from typing import List, Optional
from fastapi import APIRouter, HTTPException, Form, Body, UploadFile, File
import os
import shutil
from sqlalchemy import text
from Database.getConnection import engine
import uuid

router = APIRouter()

IMAGES_DIR = "images/"
DOMAIN_URL = "https://zonaquintas.com/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")

@router.post("/quintas", tags=["Quintas"])
async def create_quinta(
    title: str = Form(...),
    address: str = Form(...),
    latitude: float = Form(...),
    length: float = Form(...),
    city: str = Form(...),
    guests: int = Form(...),
    bedrooms: int = Form(...),
    bathrooms: int = Form(...),
    environments: str = Form(...),
    beds: int = Form(...),
    price: float = Form(...),
    images: List[UploadFile] = File(...),
    main_image: UploadFile = File(...),
    description: Optional[str] = Form(None),
    owner_id: str = Form(...),
    currency_price: str = Form(..., regex="^(ARS|USD)$"),
    created_at: Optional[str] = Form(None),
    a_a: Optional[bool] = Form(False),
    medical_kit: Optional[bool] = Form(False),
    wire: Optional[bool] = Form(False),
    kitchen: Optional[bool] = Form(False),
    cutlery: Optional[bool] = Form(False),
    parking: Optional[bool] = Form(False),
    home_stove: Optional[bool] = Form(False),
    refrigerator: Optional[bool] = Form(False),
    jacuzzi: Optional[bool] = Form(False),
    kids_games: Optional[bool] = Form(False),
    washing_machine: Optional[bool] = Form(False),
    blankets: Optional[bool] = Form(False),
    grill: Optional[bool] = Form(False),
    pool: Optional[bool] = Form(False),
    playroom: Optional[bool] = Form(False),
    camera_clothes: Optional[bool] = Form(False),
    bed_sheets: Optional[bool] = Form(False),
    dryer: Optional[bool] = Form(False),
    towels: Optional[bool] = Form(False),
    tv: Optional[bool] = Form(False),
    wifi: Optional[bool] = Form(False),
    visits: Optional[int] = Form(0),
    crockery: Optional[bool] = Form(False)
):
    quinta_id = str(uuid.uuid4())

    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR, exist_ok=True)
    ext = os.path.splitext(main_image.filename or "file.jpg")[1]
    fname = f"{uuid.uuid4()}{ext}"
    path = os.path.join(IMAGES_DIR, fname)
    with open(path, "wb") as buf:
        shutil.copyfileobj(main_image.file, buf)
    url_main = f"{DOMAIN_URL}/{fname}"

    if images:
        for img in images:
            ext = os.path.splitext(img.filename or "file.jpg")[1]
            fname = f"{uuid.uuid4()}{ext}"
            path = os.path.join(IMAGES_DIR, fname)
            with open(path, "wb") as buf:
                shutil.copyfileobj(img.file, buf)
            url = f"{DOMAIN_URL}/{fname}"
    with engine.begin() as conn:
        # Quinta
        conn.execute(
            text("""
                INSERT INTO quintas (id, title, address, latitude, length, city, guests, bedrooms, bathrooms, environments, beds, price, description, owner_id, currency_price, created_at, a_a, medical_kit, wire, kitchen, cutlery, parking, home_stove, refrigerator, jacuzzi, kids_games, washing_machine, blankets, grill, pool, playroom, camera_clothes, bed_sheets, dryer, towels, tv, wifi, visits, crockery)
                VALUES (:id, :title, :address, :latitude, :length, :city, :guests, :bedrooms, :bathrooms, :environments, :beds, :price, :description, :owner_id, :currency_price, NOW(), :a_a, :medical_kit, :wire, :kitchen, :cutlery, :parking, :home_stove, :refrigerator, :jacuzzi, :kids_games, :washing_machine, :blankets, :grill, :pool, :playroom, :camera_clothes, :bed_sheets, :dryer, :towels, :tv, :wifi, :visits, :crockery)
            """),
            {"id": quinta_id, "title": title, "address": address, "latitude": latitude, "length": length, "city": city, "guests": guests, "bedrooms": bedrooms, "bathrooms": bathrooms, "environments": environments, "beds": beds, "price": price, "description": description, "owner_id": owner_id, "currency_price": currency_price,"a_a": a_a, "medical_kit": medical_kit, "wire": wire, "kitchen": kitchen, "cutlery": cutlery, "parking": parking, "home_stove": home_stove, "refrigerator": refrigerator, "jacuzzi": jacuzzi, "kids_games": kids_games, "washing_machine": washing_machine, "blankets": blankets, "grill": grill, "pool": pool, "playroom": playroom, "camera_clothes": camera_clothes, "bed_sheets": bed_sheets, "dryer": dryer, "towels": towels, "tv": tv, "wifi": wifi, "visits": visits, "crockery": crockery},
        )

        # Main image
        conn.execute(
            text("INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
            {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
        )

        # Other images
        conn.execute(
            text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
            {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url}
        )


    return {"message": "Quinta created", "id": quinta_id, "main_image_url": url_main}

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
            quinta = result.mappings().first()
            if not quinta:
                raise HTTPException(status_code=404, detail="Quinta not found.")
            
            # Delete main image
            main_image = conn.execute(
                text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).fetchone()
            if main_image:
                main_image_path = os.path.join(IMAGES_DIR, os.path.basename(main_image[0]))
                if os.path.exists(main_image_path):
                    os.remove(main_image_path)
            conn.execute(
                text("DELETE FROM quintas_main_images WHERE quinta_id = :id"),
                {"id": quinta_id}
            )
            
            # Delete other images
            images = conn.execute(
                text("SELECT url FROM images_quintas WHERE quinta_id = :id"),
                {"id": quinta_id}
            ).scalars().all()
            for img_url in images:
                img_path = os.path.join(IMAGES_DIR, os.path.basename(img_url))
                if os.path.exists(img_path):
                    os.remove(img_path)
            conn.execute(
                text("DELETE FROM images_quintas WHERE quinta_id = :id"),
                {"id": quinta_id}
            )
            
            # Delete the quinta
            conn.execute(
                text("DELETE FROM quintas WHERE id = :id"),
                {"id": quinta_id}
            )
            
        return {"message": "Quinta and associated images deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/quintas/{quinta_id}", tags=["Quintas"])
async def update_quinta(
    quinta_id: str,
    title: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    length: Optional[float] = Form(None),
    city: Optional[str] = Form(None),
    guests: Optional[int] = Form(None),
    bedrooms: Optional[int] = Form(None),
    bathrooms: Optional[int] = Form(None),
    environments: Optional[str] = Form(None),
    beds: Optional[int] = Form(None),
    price: Optional[float] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
    main_image: Optional[UploadFile] = File(None),
    description: Optional[str] = Form(None),
    owner_id: Optional[str] = Form(None),
    currency_price: Optional[str] = Form(None, regex="^(ARS|USD)$"),
    a_a: Optional[bool] = Form(None),
    medical_kit: Optional[bool] = Form(None),
    wire: Optional[bool] = Form(None),
    kitchen: Optional[bool] = Form(None),
    cutlery: Optional[bool] = Form(None),
    parking: Optional[bool] = Form(None),
    home_stove: Optional[bool] = Form(None),
    refrigerator: Optional[bool] = Form(None),
    jacuzzi: Optional[bool] = Form(None),
    kids_games: Optional[bool] = Form(None),
    washing_machine: Optional[bool] = Form(None),
    blankets: Optional[bool] = Form(None),
    grill: Optional[bool] = Form(None),
    pool: Optional[bool] = Form(None),
    playroom: Optional[bool] = Form(None),
    camera_clothes: Optional[bool] = Form(None),
    bed_sheets: Optional[bool] = Form(None),
    dryer: Optional[bool] = Form(None),
    towels: Optional[bool] = Form(None),
    tv: Optional[bool] = Form(None),
    wifi: Optional[bool] = Form(None),
    visits: Optional[int] = Form(None),
    crockery: Optional[bool] = Form(None)
):
    try:
        if not os.path.exists(IMAGES_DIR):
            os.makedirs(IMAGES_DIR, exist_ok=True)

        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE quintas SET
                        title = :title,
                        address = :address,
                        latitude = :latitude,
                        length = :length,
                        city = :city,
                        guests = :guests,
                        bedrooms = :bedrooms,
                        bathrooms = :bathrooms,
                        environments = :environments,
                        beds = :beds,
                        price = :price,
                        description = :description,
                        owner_id = :owner_id,
                        currency_price = :currency_price,
                        a_a = :a_a,
                        medical_kit = :medical_kit,
                        wire = :wire,
                        kitchen = :kitchen,
                        cutlery = :cutlery,
                        parking = :parking,
                        home_stove = :home_stove,
                        refrigerator = :refrigerator,
                        jacuzzi = :jacuzzi,
                        kids_games = :kids_games,
                        washing_machine = :washing_machine,
                        blankets = :blankets,
                        grill = :grill,
                        pool = :pool,
                        playroom = :playroom,
                        camera_clothes = :camera_clothes,
                        bed_sheets = :bed_sheets,
                        dryer = :dryer,
                        towels = :towels,
                        tv = :tv,
                        wifi = :wifi,
                        visits = :visits,
                        crockery = :crockery                        
                    WHERE id = :id
                """),
                {
                    "id": quinta_id,
                    "title": title,
                    "address": address,
                    "latitude": latitude,
                    "length": length,
                    "city": city,
                    "guests": guests,
                    "bedrooms": bedrooms,
                    "bathrooms": bathrooms,
                    "environments": environments,
                    "beds": beds,
                    "price": price,
                    "description": description,
                    "owner_id": owner_id,
                    "currency_price": currency_price,
                    "a_a": a_a,
                    "medical_kit": medical_kit,
                    "wire": wire,
                    "kitchen": kitchen,
                    "cutlery": cutlery,
                    "parking": parking,
                    "home_stove": home_stove,
                    "refrigerator": refrigerator,
                    "jacuzzi": jacuzzi,
                    "kids_games": kids_games,
                    "washing_machine": washing_machine,
                    "blankets": blankets,
                    "grill": grill,
                    "pool": pool,
                    "playroom": playroom,
                    "camera_clothes": camera_clothes,
                    "bed_sheets": bed_sheets,
                    "dryer": dryer,
                    "towels": towels,
                    "tv": tv,
                    "wifi": wifi,
                    "visits": visits,
                    "crockery": crockery
                })
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Quinta not found.")
            
            if main_image:
                ext = os.path.splitext(main_image.filename or "file.jpg")[1]
                fname = f"{uuid.uuid4()}{ext}"
                path = os.path.join(IMAGES_DIR, fname)
                with open(path, "wb") as buf:
                    shutil.copyfileobj(main_image.file, buf)
                url_main = f"{DOMAIN_URL}/{fname}"

                conn.execute(
                    text("""
                         INSERT INTO quintas_main_images (id, quinta_id, url) VALUES (:id, :quinta_id, :url)
                         VALUES (:id, :quinta_id, :url)
                        ON DUPLICATE KEY UPDATE url = :url
                    """),
                    {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": url_main}
                )
            
            for img in images or []:
                if not hasattr(img, 'filename') or img.filename == "":
                    continue

                ext = os.path.splitext(img.filename or "file.jpg")[1]
                filename = f"{uuid.uuid4()}{ext}"
                filepath = os.path.join(IMAGES_DIR, filename)
                with open(filepath, "wb") as buf:
                    shutil.copyfileobj(img.file, buf)
                public_url = f"{DOMAIN_URL}/{filename}"

                conn.execute(
                    text("INSERT INTO images_quintas (id, quinta_id, url) VALUES (:id, :quinta_id, :url)"),
                    {"id": str(uuid.uuid4()), "quinta_id": quinta_id, "url": public_url}
                )
        
        return {"message": "Quinta updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))