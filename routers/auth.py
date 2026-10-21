from typing import List, Optional
from fastapi import APIRouter, Response, Request, HTTPException, Depends, UploadFile
from pydantic import BaseModel
from utils.security import create_access_token, get_current_user
from models.users import UserRegister, UserUpdate
from Database.getConnection import engine
from sqlalchemy import text
from utils.passwords import hash_password, password_context, verify_password
from PIL import Image
from urllib.parse import urlparse
import uuid
import os
import shutil


router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
DOMAIN_URL = os.getenv("DOMAIN_URL", "https://zonaquintas.com/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images")


def get_image_filename_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return os.path.basename(parsed.path) or ""
    except Exception:
        return ""


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
        hashed_pw = hash_password(data.password)

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
                    "role": "user",
                    "name": data.name,
                    "otime": data.owner_time,
                    "oloc": data.owner_location,
                    "avg_op": None
                }
            )
            
            # Insertar relaciones 1:N si se proporcionan
            if data.languages:
                for lang in data.languages:
                    conn.execute(
                        text("INSERT INTO users_languages (id, user_id, languages) VALUES (:id, :u_id, :lang)"),
                        {"id": str(uuid.uuid4()), "u_id": user_id, "lang": lang}
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
                
            scheme = password_context.identify(user.password_hash)
            if scheme:
                valid, needs_rehash = verify_password(data.password, user.password_hash)
                if not valid:
                    raise HTTPException(status_code=401, detail="Credenciales incorrectas.")
                if needs_rehash:
                    conn.execute(
                        text("UPDATE users SET password_hash = :pw WHERE id = :id"),
                        {"pw": hash_password(data.password), "id": user.id},
                    )
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
async def update_user(user_id: str, data: UserUpdate, current_user: str = Depends(get_current_user)):
    # Only the account owner or an authenticated administrator may edit profile fields.
    with engine.begin() as conn:
        if current_user != user_id:
            role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": current_user}).scalar()
            if (role or "").lower() not in {"admin", "superadmin"}:
                raise HTTPException(403, "No podés modificar otro usuario.")
        exists = conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id}).first()
        if not exists:
            raise HTTPException(404, "Usuario no encontrado.")
        values = data.model_dump(exclude_unset=True)
        allowed = {"email", "name", "phone", "date_of_birth", "address", "description", "owner_time", "owner_location", "review_reminders_enabled"}
        updates = {key: value for key, value in values.items() if key in allowed}
        if updates:
            set_clause = ", ".join(f"{key} = :{key}" for key in updates)
            conn.execute(text(f"UPDATE users SET {set_clause} WHERE id = :id"), {**updates, "id": user_id})
            if updates.get("review_reminders_enabled") is False:
                conn.execute(text("""
                    UPDATE review_reminders SET status='cancelled', lease_until=NULL
                    WHERE user_id=:id AND status IN ('pending', 'leased')
                """), {"id": user_id})
        if data.password:
            hashed = hash_password(data.password)
            conn.execute(text("UPDATE users SET password_hash = :pw WHERE id = :id"), {"pw": hashed, "id": user_id})
        if data.languages is not None:
            conn.execute(text("DELETE FROM users_languages WHERE user_id = :id"), {"id": user_id})
            for language in data.languages:
                conn.execute(text("INSERT INTO users_languages (id, user_id, languages) VALUES (:id, :user_id, :language)"),
                             {"id": str(uuid.uuid4()), "user_id": user_id, "language": language.lower()})
        if data.pictures is not None:
            conn.execute(text("DELETE FROM users_picture WHERE user_id = :id"), {"id": user_id})
            for picture in data.pictures:
                conn.execute(text("INSERT INTO users_picture (id, user_id, url) VALUES (:id, :user_id, :url)"),
                             {"id": str(uuid.uuid4()), "user_id": user_id, "url": picture})
    return {"message": "Usuario modificado correctamente."}


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
                user_dict.pop("password_hash", None)
                
                # Obtener relaciones 1:N
                languages = conn.execute(
                    text("SELECT languages FROM users_languages WHERE user_id = :id"), {"id": id}
                ).fetchall()
                user_dict["languages"] = [row.languages for row in languages]
                
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
async def update_user_images(user_id: str, request: Request, current_user: str = Depends(get_current_user)):
    if current_user != user_id:
        raise HTTPException(403, "No podés modificar imágenes de otro usuario.")
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
async def delete_user_picture(user_id: str, image_id: str, current_user: str = Depends(get_current_user)):
    if current_user != user_id:
        raise HTTPException(403, "No podés eliminar imágenes de otro usuario.")
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
                file_name = get_image_filename_from_url(url)
                if file_name:
                    file_path = os.path.join(IMAGES_DIR, file_name)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    else:
                        print(f"Imagen no encontrada en disco para eliminación: {file_path}")
                else:
                    print(f"URL de imagen inválida para eliminación: {url}")

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
