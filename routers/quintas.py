from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, UploadFile
import os
import shutil
from PIL import Image
from sqlalchemy import text
from Database.getConnection import engine
import uuid
import json
from models.quintas import QuintaCreate, QuintaUpdate

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
DOMAIN_URL = os.getenv("DOMAIN_URL", "https://zonaquintas.com/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images")


def save_image_to_disk(upload_file: UploadFile) -> str:
    """Guarda una imagen en disco comprimiéndola y retorna su URL pública."""
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


@router.post(
    "/quintas",
    tags=["Quintas"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["data"],
                        "properties": {
                            "data": {
                                **QuintaCreate.model_json_schema(),
                                "description": "JSON con los datos de la quinta"
                            },
                            "main_image": {
                                "type": "string",
                                "format": "binary",
                                "description": "Imagen principal de la quinta"
                            },
                            "images": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Galería de imágenes adicionales"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def create_quinta(request: Request):
    try:
        form = await request.form()

        raw_data = form.get("data")
        if not raw_data:
            raise HTTPException(status_code=422, detail="El campo 'data' es requerido.")
        try:
            quinta_data = QuintaCreate.model_validate(json.loads(raw_data))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"JSON inválido en 'data': {e}")

        main_image: Optional[UploadFile] = form.get("main_image")  # type: ignore
        images: List[UploadFile] = form.getlist("images")  # type: ignore

        quinta_id = str(uuid.uuid4())

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO quintas (
                        id, title, address, latitude, length, city, guests, bedrooms, bathrooms,
                        environments, status, payment_type, beds, price, description, owner_id, currency_price, created_at,
                        sabanas, mantas, almohadas, toilettes, shampoo, toallas, secador_pelo,
                        lavarropas, cambio_toallas, utensillos_cocina, vajilla, freezer,
                        televisor, radio, tv, cable, internet, parlantes,
                        jacuzzi, playroom, sofas,
                        estacionamiento_techado, parrilla, estufa_gas, hogar,
                        hamacas_paraguayas, arboleda, cancha_futbol, piscina,
                        cancha_basquet, cancha_tenis, cancha_padel, hamacas
                    ) VALUES (
                        :id, :title, :address, :latitude, :length, :city, :guests, :bedrooms, :bathrooms,
                        :environments, :status, :payment_type, :beds, :price, :description, :owner_id, :currency_price, NOW(),
                        :sabanas, :mantas, :almohadas, :toilettes, :shampoo, :toallas, :secador_pelo,
                        :lavarropas, :cambio_toallas, :utensillos_cocina, :vajilla, :freezer,
                        :televisor, :radio, :tv, :cable, :internet, :parlantes,
                        :jacuzzi, :playroom, :sofas,
                        :estacionamiento_techado, :parrilla, :estufa_gas, :hogar,
                        :hamacas_paraguayas, :arboleda, :cancha_futbol, :piscina,
                        :cancha_basquet, :cancha_tenis, :cancha_padel, :hamacas
                    )
                """),
                {
                    "id": quinta_id,
                    "title": quinta_data.title, "address": quinta_data.address,
                    "latitude": quinta_data.latitude, "length": quinta_data.length,
                    "status": quinta_data.status, "payment_type": quinta_data.payment_type,
                    "city": quinta_data.city, "guests": quinta_data.guests,
                    "bedrooms": quinta_data.bedrooms, "bathrooms": quinta_data.bathrooms,
                    "environments": quinta_data.environments, "beds": quinta_data.beds,
                    "price": quinta_data.price, "description": quinta_data.description,
                    "owner_id": quinta_data.owner_id, "currency_price": quinta_data.currency_price,
                    "sabanas": quinta_data.sabanas, "mantas": quinta_data.mantas,
                    "almohadas": quinta_data.almohadas, "toilettes": quinta_data.toilettes,
                    "shampoo": quinta_data.shampoo, "toallas": quinta_data.toallas,
                    "secador_pelo": quinta_data.secador_pelo, "lavarropas": quinta_data.lavarropas,
                    "cambio_toallas": quinta_data.cambio_toallas,
                    "utensillos_cocina": quinta_data.utensillos_cocina, "vajilla": quinta_data.vajilla,
                    "freezer": quinta_data.freezer,
                    "televisor": quinta_data.televisor, "radio": quinta_data.radio,
                    "tv": quinta_data.tv, "cable": quinta_data.cable,
                    "internet": quinta_data.internet, "parlantes": quinta_data.parlantes,
                    "jacuzzi": quinta_data.jacuzzi, "playroom": quinta_data.playroom,
                    "sofas": quinta_data.sofas,
                    "estacionamiento_techado": quinta_data.estacionamiento_techado,
                    "parrilla": quinta_data.parrilla, "estufa_gas": quinta_data.estufa_gas,
                    "hogar": quinta_data.hogar, "hamacas_paraguayas": quinta_data.hamacas_paraguayas,
                    "arboleda": quinta_data.arboleda, "cancha_futbol": quinta_data.cancha_futbol,
                    "piscina": quinta_data.piscina, "cancha_basquet": quinta_data.cancha_basquet,
                    "cancha_tenis": quinta_data.cancha_tenis, "cancha_padel": quinta_data.cancha_padel,
                    "hamacas": quinta_data.hamacas,
                }
            )

            url_main_response = None
            if main_image and getattr(main_image, "filename", None):
                url_main = save_image_to_disk(main_image)
                conn.execute(
                    text("INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                    {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
                )
                url_main_response = url_main

            other_image_urls = []
            for img in (images or []):
                if getattr(img, "filename", None):
                    url = save_image_to_disk(img)
                    other_image_urls.append(url)
                    conn.execute(
                        text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                        {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url}
                    )

        return {
            "message": "Quinta creada exitosamente.",
            "id": quinta_id,
            "main_image_url": url_main_response,
            "image_urls": other_image_urls,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quintas", tags=["Quintas"])
async def get_quintas():
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT * FROM quintas")).mappings().all()
            if not rows:
                return []

            quintas = []
            for quinta in rows:
                hid = quinta["id"]
                main = conn.execute(
                    text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"), {"id": hid}
                ).fetchone()
                imgs = conn.execute(
                    text("SELECT url FROM images_quintas WHERE quinta_id = :id"), {"id": hid}
                ).scalars().all()
                data = dict(quinta)
                data["main_image"] = main[0] if main else None
                data["images"] = list(imgs)
                quintas.append(data)
            return quintas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quintas/getAddressFromQuintas", tags=["Quintas"])
async def get_address_from_quintas():
    """Trae todas las direcciones y ciudades de las quintas para el buscador"""
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT address, city FROM quintas")
            ).mappings().all()

            return [dict(row) for row in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quintas/{quinta_id}", tags=["Quintas"])
async def get_quinta_by_id(quinta_id: str):
    try:
        with engine.begin() as conn:
            quinta = conn.execute(
                text("SELECT * FROM quintas WHERE id = :id"), {"id": quinta_id}
            ).mappings().first()
            if not quinta:
                raise HTTPException(status_code=404, detail="Quinta no encontrada.")

            main = conn.execute(
                text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"), {"id": quinta_id}
            ).fetchone()
            imgs = conn.execute(
                text("SELECT url FROM images_quintas WHERE quinta_id = :id"), {"id": quinta_id}
            ).scalars().all()

            data = dict(quinta)
            data["main_image"] = main[0] if main else None
            data["images"] = list(imgs)
            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/quintas/{quinta_id}", tags=["Quintas"])
async def delete_quinta(quinta_id: str):
    try:
        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone():
                raise HTTPException(status_code=404, detail="Quinta no encontrada.")

            dependencies = {
                "bookings": conn.execute(
                    text("SELECT COUNT(*) FROM bookings WHERE quinta_id = :id"), {"id": quinta_id}
                ).scalar() or 0,
                "favorites": conn.execute(
                    text("SELECT COUNT(*) FROM favorites WHERE quinta_id = :id"), {"id": quinta_id}
                ).scalar() or 0,
                "transactions": conn.execute(
                    text("SELECT COUNT(*) FROM transactions WHERE quinta_id = :id"), {"id": quinta_id}
                ).scalar() or 0,
            }
            active_dependencies = {key: value for key, value in dependencies.items() if value}
            if active_dependencies:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "No se puede eliminar la quinta porque tiene relaciones activas.",
                        "dependencies": active_dependencies,
                    },
                )

            def delete_file(url: str):
                if url:
                    path = os.path.join(IMAGES_DIR, os.path.basename(url))
                    if os.path.exists(path):
                        os.remove(path)

            main = conn.execute(
                text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"), {"id": quinta_id}
            ).fetchone()
            if main:
                delete_file(main[0])
            conn.execute(text("DELETE FROM quintas_main_images WHERE quinta_id = :id"), {"id": quinta_id})

            for img_url in conn.execute(
                text("SELECT url FROM images_quintas WHERE quinta_id = :id"), {"id": quinta_id}
            ).scalars().all():
                delete_file(img_url)
            conn.execute(text("DELETE FROM images_quintas WHERE quinta_id = :id"), {"id": quinta_id})

            conn.execute(text("DELETE FROM quintas WHERE id = :id"), {"id": quinta_id})

        return {"message": "Quinta e imágenes eliminadas exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/quintas/{quinta_id}", tags=["Quintas"])
async def update_quinta(quinta_id: str, data: QuintaUpdate):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE quintas SET
                        title = COALESCE(:title, title),
                        address = COALESCE(:address, address),
                        latitude = COALESCE(:latitude, latitude),
                        length = COALESCE(:length, length),
                        city = COALESCE(:city, city),
                        guests = COALESCE(:guests, guests),
                        bedrooms = COALESCE(:bedrooms, bedrooms),
                        bathrooms = COALESCE(:bathrooms, bathrooms),
                        environments = COALESCE(:environments, environments),
                        beds = COALESCE(:beds, beds),
                        price = COALESCE(:price, price),
                        description = COALESCE(:description, description),
                        owner_id = COALESCE(:owner_id, owner_id),
                        currency_price = COALESCE(:currency_price, currency_price),
                        sabanas = COALESCE(:sabanas, sabanas),
                        mantas = COALESCE(:mantas, mantas),
                        almohadas = COALESCE(:almohadas, almohadas),
                        toilettes = COALESCE(:toilettes, toilettes),
                        shampoo = COALESCE(:shampoo, shampoo),
                        toallas = COALESCE(:toallas, toallas),
                        secador_pelo = COALESCE(:secador_pelo, secador_pelo),
                        lavarropas = COALESCE(:lavarropas, lavarropas),
                        cambio_toallas = COALESCE(:cambio_toallas, cambio_toallas),
                        utensillos_cocina = COALESCE(:utensillos_cocina, utensillos_cocina),
                        vajilla = COALESCE(:vajilla, vajilla),
                        freezer = COALESCE(:freezer, freezer),
                        televisor = COALESCE(:televisor, televisor),
                        radio = COALESCE(:radio, radio),
                        tv = COALESCE(:tv, tv),
                        cable = COALESCE(:cable, cable),
                        internet = COALESCE(:internet, internet),
                        parlantes = COALESCE(:parlantes, parlantes),
                        jacuzzi = COALESCE(:jacuzzi, jacuzzi),
                        playroom = COALESCE(:playroom, playroom),
                        sofas = COALESCE(:sofas, sofas),
                        estacionamiento_techado = COALESCE(:estacionamiento_techado, estacionamiento_techado),
                        parrilla = COALESCE(:parrilla, parrilla),
                        estufa_gas = COALESCE(:estufa_gas, estufa_gas),
                        hogar = COALESCE(:hogar, hogar),
                        hamacas_paraguayas = COALESCE(:hamacas_paraguayas, hamacas_paraguayas),
                        arboleda = COALESCE(:arboleda, arboleda),
                        cancha_futbol = COALESCE(:cancha_futbol, cancha_futbol),
                        piscina = COALESCE(:piscina, piscina),
                        cancha_basquet = COALESCE(:cancha_basquet, cancha_basquet),
                        cancha_tenis = COALESCE(:cancha_tenis, cancha_tenis),
                        cancha_padel = COALESCE(:cancha_padel, cancha_padel),
                        hamacas = COALESCE(:hamacas, hamacas)
                    WHERE id = :id
                """),
                {
                    "id": quinta_id,
                    "title": data.title, "address": data.address, "latitude": data.latitude,
                    "length": data.length, "city": data.city, "guests": data.guests,
                    "bedrooms": data.bedrooms, "bathrooms": data.bathrooms,
                    "environments": data.environments, "beds": data.beds,
                    "price": data.price, "description": data.description,
                    "owner_id": data.owner_id, "currency_price": data.currency_price,
                    "sabanas": data.sabanas, "mantas": data.mantas, "almohadas": data.almohadas,
                    "toilettes": data.toilettes, "shampoo": data.shampoo, "toallas": data.toallas,
                    "secador_pelo": data.secador_pelo, "lavarropas": data.lavarropas,
                    "cambio_toallas": data.cambio_toallas,
                    "utensillos_cocina": data.utensillos_cocina, "vajilla": data.vajilla,
                    "freezer": data.freezer,
                    "televisor": data.televisor, "radio": data.radio, "tv": data.tv,
                    "cable": data.cable, "internet": data.internet, "parlantes": data.parlantes,
                    "jacuzzi": data.jacuzzi, "playroom": data.playroom, "sofas": data.sofas,
                    "estacionamiento_techado": data.estacionamiento_techado,
                    "parrilla": data.parrilla, "estufa_gas": data.estufa_gas, "hogar": data.hogar,
                    "hamacas_paraguayas": data.hamacas_paraguayas, "arboleda": data.arboleda,
                    "cancha_futbol": data.cancha_futbol, "piscina": data.piscina,
                    "cancha_basquet": data.cancha_basquet, "cancha_tenis": data.cancha_tenis,
                    "cancha_padel": data.cancha_padel, "hamacas": data.hamacas,
                }
            )

            if result.rowcount == 0:
                if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone():
                    raise HTTPException(status_code=404, detail="Quinta no encontrada.")

        return {"message": "Quinta actualizada exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/quintas/{quinta_id}/images",
    tags=["Quintas"],
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "main_image": {
                                "type": "string",
                                "format": "binary",
                                "description": "Nueva imagen principal (reemplaza la existente)"
                            },
                            "images": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Imágenes adicionales a agregar a la galería"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def update_quinta_images(quinta_id: str, request: Request):
    try:
        form = await request.form()
        main_image: Optional[UploadFile] = form.get("main_image")  # type: ignore
        images: List[UploadFile] = form.getlist("images")  # type: ignore

        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone():
                raise HTTPException(status_code=404, detail="Quinta no encontrada.")

            if main_image and getattr(main_image, "filename", None):
                url_main = save_image_to_disk(main_image)
                res = conn.execute(
                    text("UPDATE quintas_main_images SET url = :url WHERE quinta_id = :id"),
                    {"url": url_main, "id": quinta_id}
                )
                if res.rowcount == 0:
                    conn.execute(
                        text("INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                        {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
                    )

            for img in images:
                if getattr(img, "filename", None):
                    public_url = save_image_to_disk(img)
                    conn.execute(
                        text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                        {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": public_url}
                    )

        return {"message": "Imágenes actualizadas exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
