from typing import List, Optional
from fastapi import APIRouter, HTTPException, Form, UploadFile, File
import os
import shutil
from PIL import Image
from sqlalchemy import text
from Database.getConnection import engine
import uuid
from fastapi import Depends, HTTPException, UploadFile, File
from models.quintas import QuintaCreate, QuintaUpdate
from utils.security import get_current_user

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
DOMAIN_URL = os.getenv("DOMAIN_URL", "https://zonaquintas.com/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images")

def save_image_to_disk(upload_file: UploadFile) -> str:
    """Helper function to save an uploaded image to disk, compressing it, and return its public URL."""
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        
    ext = os.path.splitext(upload_file.filename or "file.jpg")[1].lower()
    # Forces conversion to WebP or optimized JPEG to save space
    fname = f"{uuid.uuid4()}{ext}"
    path = os.path.join(IMAGES_DIR, fname)
    
    try:
        # Open image using Pillow
        image = Image.open(upload_file.file)

        # Convert to RGB if it's RGBA or P to avoid issues when saving as JPEG
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
            
        # Resize if width or height > 1920 preserving aspect ratio
        max_size = (1920, 1080)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save compressed
        # Use webp if you'd like, or stick to standard jpeg/png depending on extension
        if ext in [".jpg", ".jpeg"]:
            image.save(path, format="JPEG", optimize=True, quality=80)
        elif ext == ".png":
            image.save(path, format="PNG", optimize=True)
        else:
            image.save(path) # fallback
            
    except Exception as e:
        # Fallback to pure copy if Pillow fails to parse it
        upload_file.file.seek(0)
        with open(path, "wb") as buf:
            shutil.copyfileobj(upload_file.file, buf)

    return f"{DOMAIN_URL}/{fname}"

@router.post("/quintas", tags=["Quintas"])
async def create_quinta(
    data: QuintaCreate,
    current_user: str = Depends(get_current_user),
):
    try:
        quinta_id = str(uuid.uuid4())

        with engine.begin() as conn:
            # Quinta
            conn.execute(
                text("""
                    INSERT INTO quintas (id, title, address, latitude, length, city, guests, bedrooms, bathrooms, environments, beds, price, description, owner_id, currency_price, created_at, a_a, medical_kit, wire, kitchen, cutlery, parking, home_stove, refrigerator, jacuzzi, kids_games, washing_machine, blankets, grill, pool, playroom, camera_clothes, bed_sheets, dryer, towels, tv, wifi, visits, crockery)
                    VALUES (:id, :title, :address, :latitude, :length, :city, :guests, :bedrooms, :bathrooms, :environments, :beds, :price, :description, :owner_id, :currency_price, NOW(), :a_a, :medical_kit, :wire, :kitchen, :cutlery, :parking, :home_stove, :refrigerator, :jacuzzi, :kids_games, :washing_machine, :blankets, :grill, :pool, :playroom, :camera_clothes, :bed_sheets, :dryer, :towels, :tv, :wifi, :visits, :crockery)
                """),
                {
                    "id": quinta_id, "title": data.title, "address": data.address, "latitude": data.latitude, "length": data.length, "city": data.city, 
                    "guests": data.guests, "bedrooms": data.bedrooms, "bathrooms": data.bathrooms, "environments": data.environments, "beds": data.beds, 
                    "price": data.price, "description": data.description, "owner_id": data.owner_id, "currency_price": data.currency_price,
                    "a_a": data.a_a, "medical_kit": data.medical_kit, "wire": data.wire, "kitchen": data.kitchen, "cutlery": data.cutlery, "parking": data.parking, 
                    "home_stove": data.home_stove, "refrigerator": data.refrigerator, "jacuzzi": data.jacuzzi, "kids_games": data.kids_games, 
                    "washing_machine": data.washing_machine, "blankets": data.blankets, "grill": data.grill, "pool": data.pool, "playroom": data.playroom, 
                    "camera_clothes": data.camera_clothes, "bed_sheets": data.bed_sheets, "dryer": data.dryer, "towels": data.towels, "tv": data.tv, 
                    "wifi": data.wifi, "visits": data.visits, "crockery": data.crockery
                }
            )

        return {"message": "Quinta created successfully", "id": quinta_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quintas/{quinta_id}/images", tags=["Quintas"])
async def upload_quinta_images(
    quinta_id: str,
    main_image: UploadFile = File(...),
    images: Optional[List[UploadFile]] = File(None),
    current_user: str = Depends(get_current_user),
):
    try:
        # Check if quinta exists
        with engine.begin() as conn:
            check = conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone()
            if not check:
                raise HTTPException(status_code=404, detail="Quinta no encontrada para sumarle imágenes")

            # Save main image
            url_main = save_image_to_disk(main_image)
            conn.execute(
                text("INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
            )

            # Save other images
            other_image_urls = []
            if images:
                for img in images:
                    if getattr(img, "filename", None):
                        url = save_image_to_disk(img)
                        other_image_urls.append(url)
            
            for url in other_image_urls:
                conn.execute(
                    text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                    {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url}
                )

        return {"message": "Imágenes asociadas correctamente", "main_image_url": url_main}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quintas", tags=["Quintas"])
async def get_quintas():
    try:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT * FROM quintas"))
            rows = result.mappings().all()
            if not rows:
                raise HTTPException(status_code=404, detail="No quintas found.")
            
            quintas = []
            for quinta in rows:
                hid = quinta["id"]
                main = conn.execute(
                    text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"),
                    {"id": hid}
                ).fetchone()
                images = conn.execute(
                    text("SELECT url FROM images_quintas WHERE quinta_id = :id"),
                    {"id": hid}
                ).scalars().all()
                
                data = dict(quinta)
                data["main_image"] = main[0] if main else None
                data["images"] = images
                quintas.append(data)
            return quintas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/quintas/{quinta_id}", tags=["Quintas"])
async def get_quinta_by_id(quinta_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT * FROM quintas WHERE id = :id"),
                {"id": quinta_id}
            )
            quinta = result.mappings().first()
            if not quinta:
                raise HTTPException(status_code=404, detail="Quinta not found.")
            
            main = conn.execute(
                text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).fetchone()
            images = conn.execute(
                text("SELECT url FROM images_quintas WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).scalars().all()
            
            data = dict(quinta)
            data["main_image"] = main[0] if main else None
            data["images"] = images
            return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/quintas/{quinta_id}", tags=["Quintas"])
async def delete_quinta(quinta_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT * FROM quintas WHERE id = :id"),
                {"id": quinta_id}
            )
            if not result.mappings().first():
                raise HTTPException(status_code=404, detail="Quinta not found.")
            
            # Helper to delete file
            def delete_file_from_url(url: str):
                if url:
                    file_path = os.path.join(IMAGES_DIR, os.path.basename(url))
                    if os.path.exists(file_path):
                        os.remove(file_path)

            # Fetch and delete main image
            main_image = conn.execute(
                text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).fetchone()
            if main_image:
                delete_file_from_url(main_image[0])
            conn.execute(text("DELETE FROM quintas_main_images WHERE quinta_id = :id"), {"id": quinta_id})
            
            # Fetch and delete other images
            images = conn.execute(
                text("SELECT url FROM images_quintas WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).scalars().all()
            for img_url in images:
                delete_file_from_url(img_url)
            conn.execute(text("DELETE FROM images_quintas WHERE quinta_id = :id"), {"id": quinta_id})
            
            # Delete the quinta
            conn.execute(text("DELETE FROM quintas WHERE id = :id"), {"id": quinta_id})
            
        return {"message": "Quinta and associated images deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/quintas/{quinta_id}", tags=["Quintas"])
async def update_quinta(
    quinta_id: str,
    data: QuintaUpdate,
    current_user: str = Depends(get_current_user),
):
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
                        a_a = COALESCE(:a_a, a_a),
                        medical_kit = COALESCE(:medical_kit, medical_kit),
                        wire = COALESCE(:wire, wire),
                        kitchen = COALESCE(:kitchen, kitchen),
                        cutlery = COALESCE(:cutlery, cutlery),
                        parking = COALESCE(:parking, parking),
                        home_stove = COALESCE(:home_stove, home_stove),
                        refrigerator = COALESCE(:refrigerator, refrigerator),
                        jacuzzi = COALESCE(:jacuzzi, jacuzzi),
                        kids_games = COALESCE(:kids_games, kids_games),
                        washing_machine = COALESCE(:washing_machine, washing_machine),
                        blankets = COALESCE(:blankets, blankets),
                        grill = COALESCE(:grill, grill),
                        pool = COALESCE(:pool, pool),
                        playroom = COALESCE(:playroom, playroom),
                        camera_clothes = COALESCE(:camera_clothes, camera_clothes),
                        bed_sheets = COALESCE(:bed_sheets, bed_sheets),
                        dryer = COALESCE(:dryer, dryer),
                        towels = COALESCE(:towels, towels),
                        tv = COALESCE(:tv, tv),
                        wifi = COALESCE(:wifi, wifi),
                        visits = COALESCE(:visits, visits),
                        crockery = COALESCE(:crockery, crockery)                        
                    WHERE id = :id
                """),
                {
                    "id": quinta_id, "title": data.title, "address": data.address, "latitude": data.latitude, "length": data.length,
                    "city": data.city, "guests": data.guests, "bedrooms": data.bedrooms, "bathrooms": data.bathrooms, "environments": data.environments,
                    "beds": data.beds, "price": data.price, "description": data.description, "owner_id": data.owner_id, "currency_price": data.currency_price,
                    "a_a": data.a_a, "medical_kit": data.medical_kit, "wire": data.wire, "kitchen": data.kitchen, "cutlery": data.cutlery,
                    "parking": data.parking, "home_stove": data.home_stove, "refrigerator": data.refrigerator, "jacuzzi": data.jacuzzi,
                    "kids_games": data.kids_games, "washing_machine": data.washing_machine, "blankets": data.blankets, "grill": data.grill,
                    "pool": data.pool, "playroom": data.playroom, "camera_clothes": data.camera_clothes, "bed_sheets": data.bed_sheets,
                    "dryer": data.dryer, "towels": data.towels, "tv": data.tv, "wifi": data.wifi, "visits": data.visits, "crockery": data.crockery
                }
            )
            
            if result.rowcount == 0:
                # Let's double check if it's 404 or just no changes made.
                check = conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone()
                if not check:
                    raise HTTPException(status_code=404, detail="Quinta not found.")
        
        return {"message": "Quinta updated successfully (metadata/JSON changes)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/quintas/{quinta_id}/images", tags=["Quintas"])
async def update_quinta_images(
    quinta_id: str,
    main_image: Optional[UploadFile] = File(None),
    images: Optional[List[UploadFile]] = File(None),
    current_user: str = Depends(get_current_user),
):
    try:
        with engine.begin() as conn:
            check = conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone()
            if not check:
                raise HTTPException(status_code=404, detail="Quinta not found.")
            
            if main_image and getattr(main_image, "filename", None):
                url_main = save_image_to_disk(main_image)
                res = conn.execute(
                    text("UPDATE quintas_main_images SET url = :url WHERE quinta_id = :quinta_id"),
                    {"url": url_main, "quinta_id": quinta_id}
                )
                if res.rowcount == 0:
                    conn.execute(
                        text("INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                        {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
                    )
            
            for img in images or []:
                if getattr(img, "filename", None):
                    public_url = save_image_to_disk(img)
                    conn.execute(
                        text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                        {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": public_url}
                    )
        
        return {"message": "Quinta images updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))