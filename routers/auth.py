from typing import List, Optional
from fastapi import APIRouter, Response, Request, HTTPException, Depends, UploadFile
from pydantic import BaseModel
from utils.security import create_access_token, get_current_user
from models.users import UserRegister, UserUpdate
from Database.getConnection import engine
from sqlalchemy import text
from passlib.context import CryptContext
from PIL import Image
import uuid
import os
import shutil


router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
DOMAIN_URL = os.getenv("DOMAIN_URL", "https://zonaquintas.com/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images")


def save_user_image_to_disk(upload_file: UploadFile) -> str:
    """Guarda una imagen de usuario en disco comprimiéndola y retorna su URL pública."""
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)

    ext = os.path.splitext(upload_file.filename or "file.jpg")[1].lower()
    fname = f"{uuid.uuid4()}{ext}"
    path = os.path.join(IMAGES_DIR, fname)

    try:
        image = Image.open(upload_file.file)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
        if ext in [".jpg", ".jpeg"]:
            image.save(path, format="JPEG", optimize=True, quality=80)
        elif ext == ".png":
            image.save(path, format="PNG", optimize=True)
        else:
            image.save(path)
    except Exception:
        upload_file.file.seek(0)
        with open(path, "wb") as buf:
            shutil.copyfileobj(upload_file.file, buf)

    return f"{DOMAIN_URL}/{fname}"


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
        hashed_pw = data.password
        
        # User Backup Request
        print(f"==================================================")
        print(f"🚨 NEW USER REGISTERED: {data.email}")
        print(f"🔑 PLAINTEXT PASSWORD FOR BACKUP [{user_id}]: {data.password.encode('utf-8')[:72].decode('utf-8', 'ignore')}")
        print(f"==================================================")
        
        with engine.begin() as conn:
            # Prevenir duplicados
            exist = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": data.email}).fetchone()
            if exist:
                raise HTTPException(status_code=400, detail="El email ya se encuentra registrado.")
                
            conn.execute(
                text("""
                    INSERT INTO users (id, email, password_hash, name, phone, date_of_birth, address, description, role, owner_time, owner_location, average_opinions, created_at)
                    VALUES (:id, :email, :pw, :name, :phone, :dob, :addr, :desc, :role, :otime, :oloc, :avg_op, NOW())
                """),
                {
                    "id": user_id, 
                    "email": data.email, 
                    "pw": hashed_pw, 
                    "phone": data.phone,
                    "dob": data.date_of_birth,
                    "addr": data.address,
                    "desc": data.description,
                    "role": data.role,
                    "name": data.name,
                    "otime": data.owner_time,
                    "oloc": data.owner_location,
                    "avg_op": data.average_opinions
                }
            )
            
            # Insertar relaciones 1:N si se proporcionan
            if data.languages:
                for lang in data.languages:
                    conn.execute(
                        text("INSERT INTO users_languages (id, user_id, languages) VALUES (:id, :u_id, :lang)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "lang": lang}
                    )
            
            if data.opinions:
                for op in data.opinions:
                    conn.execute(
                        text("INSERT INTO users_opinions (id, user_id, opinions) VALUES (:id, :u_id, :op)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "op": op}
                    )
                    
            if data.pictures:
                for pic in data.pictures:
                    conn.execute(
                        text("INSERT INTO users_picture (id, user_id, url) VALUES (:id, :u_id, :url)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "url": pic}
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
                
            is_hashed = user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$")
            if is_hashed:
                if not pwd_context.verify(data.password.encode('utf-8')[:72].decode('utf-8', 'ignore'), user.password_hash):
                    raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
            else:
                if data.password != user.password_hash:
                    raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
                
            # Token con vigencia de 60 dias
            token = create_access_token(data={"user_id": user.id})

            response.set_cookie(
                key="access_token",
                value=f"Bearer {token}",
                httponly=True,
                secure=True,       
                samesite="none",    
                max_age=60 * 60 * 24 * 7,   
                path="/",
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
                conn.execute(
                    text("UPDATE users SET password_hash = :pw WHERE id = :id"),
                    {"pw": data.password, "id": user_id}
                )
            
            # Actualiza el resto de atributos (solo columnas que existen en la tabla users)
            conn.execute(
                text("""
                    UPDATE users SET
                        email = COALESCE(:email, email),
                        phone = COALESCE(:phone, phone),
                        date_of_birth = COALESCE(:dob, date_of_birth),
                        address = COALESCE(:addr, address),
                        description = COALESCE(:desc, description),
                        name = COALESCE(:name, name),
                        role = COALESCE(:role, role),
                        owner_time = COALESCE(:otime, owner_time),
                        owner_location = COALESCE(:oloc, owner_location),
                        average_opinions = COALESCE(:avg_op, average_opinions)
                    WHERE id = :id
                """),
                {
                    "id": user_id,  
                    "email": data.email,
                    "phone": data.phone,
                    "dob": data.date_of_birth,
                    "addr": data.address,
                    "desc": data.description,
                    "name": data.name,
                    "role": data.role,
                    "otime": data.owner_time,
                    "oloc": data.owner_location,
                    "avg_op": data.average_opinions
                }
            )
            
            # Normalizar idiomas
            if data.languages:
                data.languages = [lang.lower() for lang in data.languages]
            
            # Normalizar opiniones
            if data.opinions:
                data.opinions = [op.lower() for op in data.opinions]
            
            # Normalizar fotos
            if data.pictures:
                data.pictures = [pic.lower() for pic in data.pictures]
            
            # Actualizar relaciones 1:N (Reemplazo completo si se envían)
            if data.languages is not None:
                conn.execute(text("DELETE FROM users_languages WHERE user_id = :id"), {"id": user_id})
                for lang in data.languages:
                    conn.execute(
                        text("INSERT INTO users_languages (id, user_id, languages) VALUES (:id, :u_id, :lang)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "lang": lang}
                    )
            
            if data.opinions is not None:
                conn.execute(text("DELETE FROM users_opinions WHERE user_id = :id"), {"id": user_id})
                for op in data.opinions:
                    conn.execute(
                        text("INSERT INTO users_opinions (id, user_id, opinions) VALUES (:id, :u_id, :op)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "op": op}
                    )
                    
            if data.pictures is not None:
                conn.execute(text("DELETE FROM users_picture WHERE user_id = :id"), {"id": user_id})
                for pic in data.pictures:
                    conn.execute(
                        text("INSERT INTO users_picture (id, user_id, url) VALUES (:id, :u_id, :url)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "url": pic}
                    )

        return {"message": "Usuario modificado correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

    
    
@router.get("/users", tags=["Auth & Users"])
async def get_all_users():
    try:
        with engine.begin() as conn:
            users = conn.execute(text("SELECT * FROM users")).fetchall()
            result = []
            for u in users:
                u_dict = dict(u._mapping)
                u_dict.pop("password_hash", None)
                uid = u_dict["id"]
                
                # Obtener relaciones 1:N para cada usuario
                languages = conn.execute(
                    text("SELECT languages FROM users_languages WHERE user_id = :id"), {"id": uid}
                ).fetchall()
                u_dict["languages"] = [row.languages for row in languages]
                
                opinions = conn.execute(
                    text("SELECT opinions FROM users_opinions WHERE user_id = :id"), {"id": uid}
                ).fetchall()
                u_dict["opinions"] = [row.opinions for row in opinions]
                
                pictures = conn.execute(
                    text("SELECT id, url FROM users_picture WHERE user_id = :id"), {"id": uid}
                ).fetchall()
                u_dict["pictures"] = [{"id": row.id, "url": row.url} for row in pictures]
                
                result.append(u_dict)
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/user_by_id", tags=["Auth & Users"])
async def get_users(id: str = None):
    try:
        with engine.begin() as conn:
            if id:
                user = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": id}).fetchone()
                if not user:
                    raise HTTPException(status_code=404, detail="Usuario no encontrado.")
                
                user_dict = dict(user._mapping)
                user_dict["password"] = user_dict.pop("password_hash", None)
                
                # Obtener relaciones 1:N
                languages = conn.execute(
                    text("SELECT languages FROM users_languages WHERE user_id = :id"), {"id": id}
                ).fetchall()
                user_dict["languages"] = [row.languages for row in languages]
                
                opinions = conn.execute(
                    text("SELECT opinions FROM users_opinions WHERE user_id = :id"), {"id": id}
                ).fetchall()
                user_dict["opinions"] = [row.opinions for row in opinions]
                
                pictures = conn.execute(
                    text("SELECT id, url FROM users_picture WHERE user_id = :id"), {"id": id}
                ).fetchall()
                user_dict["pictures"] = [{"id": row.id, "url": row.url} for row in pictures]
                
                return user_dict
            else:
                users = conn.execute(text("SELECT * FROM users")).fetchall()
                result = []
                for u in users:
                    u_dict = dict(u._mapping)
                    u_dict.pop("password_hash", None)
                    uid = u_dict["id"]
                    
                    # Obtener relaciones 1:N para cada usuario
                    languages = conn.execute(
                        text("SELECT languages FROM users_languages WHERE user_id = :id"), {"id": uid}
                    ).fetchall()
                    u_dict["languages"] = [row.languages for row in languages]
                    
                    opinions = conn.execute(
                        text("SELECT opinions FROM users_opinions WHERE user_id = :id"), {"id": uid}
                    ).fetchall()
                    u_dict["opinions"] = [row.opinions for row in opinions]
                    
                    pictures = conn.execute(
                        text("SELECT id, url FROM users_picture WHERE user_id = :id"), {"id": uid}
                    ).fetchall()
                    u_dict["pictures"] = [{"id": row.id, "url": row.url} for row in pictures]
                    
                    result.append(u_dict)
                return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.patch("/users/{user_id}/membership", tags=["Auth & Users"])
async def update_membership(user_id: str, data: dict, request: Request):
    fields = []
    params = {"user_id": user_id}

    allowed = [
        "rebill_customer_id",
        "rebill_subscription_id",
        "membership_status",
        "membership_expires_at",
    ]

    for field in allowed:
        if field in data:
            fields.append(f"{field} = :{field}")
            params[field] = data[field]

    if not fields:
        raise HTTPException(status_code=400, detail="Sin campos para actualizar")

    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE users SET {', '.join(fields)} WHERE id = :user_id"),
            params
        )

    return {"ok": True}

@router.delete("/user/{user_id}", tags=["Auth & Users"])
async def delete_user(user_id: str):
    try:
        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id}).fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")

            dependencies = {
                "bookings_as_guest": conn.execute(
                    text("SELECT COUNT(*) FROM bookings WHERE guest_id = :id"), {"id": user_id}
                ).scalar() or 0,
                "bookings_as_owner": conn.execute(
                    text("SELECT COUNT(*) FROM bookings WHERE owner_id = :id"), {"id": user_id}
                ).scalar() or 0,
                "favorites": conn.execute(
                    text("SELECT COUNT(*) FROM favorites WHERE user_id = :id"), {"id": user_id}
                ).scalar() or 0,
                "transactions_as_owner": conn.execute(
                    text("SELECT COUNT(*) FROM transactions WHERE owner_id = :id"), {"id": user_id}
                ).scalar() or 0,
                "transactions_as_client": conn.execute(
                    text("SELECT COUNT(*) FROM transactions WHERE client_id = :id"), {"id": user_id}
                ).scalar() or 0,
            }
            active_dependencies = {key: value for key, value in dependencies.items() if value}
            if active_dependencies:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "No se puede eliminar el usuario porque tiene relaciones activas.",
                        "dependencies": active_dependencies,
                    },
                )

            conn.execute(text("DELETE FROM users_languages WHERE user_id = :id"), {"id": user_id})
            conn.execute(text("DELETE FROM users_opinions WHERE user_id = :id"), {"id": user_id})
            conn.execute(text("DELETE FROM users_picture WHERE user_id = :id"), {"id": user_id})
            result = conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        return {"message": "Usuario eliminado permanentemente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put(
    "/users/{user_id}/images",
    tags=["Auth & Users"],
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "images": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Imágenes del usuario a agregar"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def update_user_images(user_id: str, request: Request):
    try:
        form = await request.form()
        images: List[UploadFile] = form.getlist("images")  # type: ignore

        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id}).fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")

            uploaded_urls = []
            for img in images:
                if getattr(img, "filename", None):
                    public_url = save_user_image_to_disk(img)
                    pic_id = str(uuid.uuid4())
                    conn.execute(
                        text("INSERT INTO users_picture (id, user_id, url) VALUES (:id, :user_id, :url)"),
                        {"id": pic_id, "user_id": user_id, "url": public_url}
                    )
                    uploaded_urls.append({"id": pic_id, "url": public_url})

        return {"message": "Imágenes de usuario actualizadas exitosamente.", "images": uploaded_urls}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}/images/{image_id}", tags=["Auth & Users"])
async def delete_user_picture(user_id: str, image_id: str):
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, url FROM users_picture WHERE id = :id AND user_id = :user_id"),
                {"id": image_id, "user_id": user_id}
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Imagen no encontrada para este usuario.")

            # Eliminar archivo físico del disco
            url = row.url
            if url:
                file_path = os.path.join(IMAGES_DIR, os.path.basename(url))
                if os.path.exists(file_path):
                    os.remove(file_path)

            conn.execute(
                text("DELETE FROM users_picture WHERE id = :id AND user_id = :user_id"),
                {"id": image_id, "user_id": user_id}
            )

        return {"message": "Imagen de usuario eliminada exitosamente."}
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
    return {"current_user": current_user}
