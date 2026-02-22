from fastapi import APIRouter, Response, HTTPException, Depends
from pydantic import BaseModel
from utils.security import create_access_token, get_current_user
from models.users import UserRegister, UserUpdate
from Database.getConnection import engine
from sqlalchemy import text
from passlib.context import CryptContext
import uuid

router = APIRouter()

# Setup Passlib for secure hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def ensure_users_table_has_password():
    """Valida y emparcha la tabla users original del cliente agregando el campo faltante"""
    try:
        with engine.begin() as conn:
            # Revisa si la columna existe en base al Information Schema de MySQL
            result = conn.execute(
                text("SHOW COLUMNS FROM `users` LIKE 'password_hash'")
            )
            if not result.fetchone():
                print("Patching DB: Adding password_hash to users table...")
                conn.execute(text("ALTER TABLE `users` ADD COLUMN `password_hash` VARCHAR(255) NULL"))
    except Exception as e:
        print(f"Error checking/patching users table constraints: {e}")

# Ejecutamos el parcheo de base de datos al importar el router
ensure_users_table_has_password()

class LoginData(BaseModel):
    email: str
    password: str

@router.post("/register", tags=["Auth & Users"])
async def register_user(data: UserRegister):
    try:
        user_id = str(uuid.uuid4())
        hashed_pw = pwd_context.hash(data.password)
        
        # User Backup Request
        print(f"==================================================")
        print(f"🚨 NEW USER REGISTERED: {data.email}")
        print(f"🔑 PLAINTEXT PASSWORD FOR BACKUP [{user_id}]: {data.password}")
        print(f"==================================================")
        
        with engine.begin() as conn:
            # Prevenir duplicados
            exist = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": data.email}).fetchone()
            if exist:
                raise HTTPException(status_code=400, detail="El email ya se encuentra registrado.")
                
            conn.execute(
                text("""
                    INSERT INTO users (id, name, email, password_hash, phone, date_of_birth, address, description, role, created_at)
                    VALUES (:id, :name, :email, :pw, :phone, :dob, :addr, :desc, :role, NOW())
                """),
                {
                    "id": user_id, 
                    "name": data.name,
                    "email": data.email, 
                    "pw": hashed_pw, 
                    "phone": data.phone,
                    "dob": data.date_of_birth,
                    "addr": data.address,
                    "desc": data.description,
                    "role": data.role
                }
            )
        return {"message": "Usuario registrado exitosamente.", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", tags=["Auth & Users"])
async def login(data: LoginData, response: Response):
    try:
        with engine.begin() as conn:
            user = conn.execute(
                text("SELECT id, password_hash FROM users WHERE email = :email"),
                {"email": data.email}
            ).fetchone()
            
            if not user or not user.password_hash:
                raise HTTPException(status_code=401, detail="Credenciales incorrectas o usuario no existe.")
                
            if not pwd_context.verify(data.password, user.password_hash):
                raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
                
            # Token con vigencia de 60 dias
            token = create_access_token(data={"sub": user.id})

            response.set_cookie(
                key="access_token",
                value=f"Bearer {token}",
                httponly=True,
                max_age=5184000,
                samesite="lax",
                secure=False,
            )
            return {"message": "Sesion iniciada correctamente. Cookie guardada.", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/user/{user_id}", tags=["Auth & Users"])
async def update_user(user_id: str, data: UserUpdate):
    try:
        with engine.begin() as conn:
            # Chequeamos si actualiza contraseña independientemente
            if data.password:
                hashed_pw = pwd_context.hash(data.password)
                conn.execute(
                    text("UPDATE users SET password_hash = :pw WHERE id = :id"),
                    {"pw": hashed_pw, "id": user_id}
                )
            
            # Actualiza el resto de atributos
            conn.execute(
                text("""
                    UPDATE users SET
                        email = COALESCE(:email, email),
                        phone = COALESCE(:phone, phone),
                        date_of_birth = COALESCE(:dob, date_of_birth),
                        address = COALESCE(:addr, address),
                        description = COALESCE(:desc, description),
                        role = COALESCE(:role, role)
                    WHERE id = :id
                """),
                {
                    "id": user_id,
                    "email": data.email,
                    "phone": data.phone,
                    "dob": data.date_of_birth,
                    "addr": data.address,
                    "desc": data.description,
                    "role": data.role
                }
            )
        return {"message": "Usuario modificado correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.delete("/user/{user_id}", tags=["Auth & Users"])
async def delete_user(user_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        return {"message": "Usuario eliminado permanentemente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout", tags=["Auth & Users"])
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Sesion cerrada correctamente."}

@router.get("/me", tags=["Auth & Users"])
async def protect_route(current_user: str = Depends(get_current_user)):
    return {"message": f"Estas logueado bajo la identidad persistente {current_user}"}
