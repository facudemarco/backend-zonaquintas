import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from Database.getConnection import engine
from models.favorites import FavoriteCreate

router = APIRouter()


@router.post("/favorites", tags=["Favorites"])
async def add_favorite(data: FavoriteCreate):
    try:
        favorite_id = str(uuid.uuid4())
        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": data.user_id}).fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
            if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": data.quinta_id}).fetchone():
                raise HTTPException(status_code=404, detail="Quinta no encontrada.")
            existing = conn.execute(
                text("SELECT id FROM favorites WHERE user_id = :user_id AND quinta_id = :quinta_id"),
                {"user_id": data.user_id, "quinta_id": data.quinta_id},
            ).fetchone()
            if existing:
                return {"message": "La quinta ya estaba en favoritos.", "id": existing.id}

            conn.execute(
                text("INSERT INTO favorites (id, user_id, quinta_id, created_at) VALUES (:id, :user_id, :quinta_id, NOW())"),
                {"id": favorite_id, "user_id": data.user_id, "quinta_id": data.quinta_id},
            )
        return {"message": "Favorito agregado correctamente.", "id": favorite_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/favorites/{user_id}", tags=["Favorites"])
async def get_user_favorites(user_id: str):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT f.id AS favorite_id, f.created_at AS favorite_created_at,
                           q.*, qmi.url AS main_image
                    FROM favorites f
                    INNER JOIN quintas q ON f.quinta_id = q.id
                    LEFT JOIN quintas_main_images qmi ON qmi.quinta_id = q.id
                    WHERE f.user_id = :user_id
                    ORDER BY f.created_at DESC
                """),
                {"user_id": user_id},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/favorites/{user_id}/{quinta_id}", tags=["Favorites"])
async def remove_favorite(user_id: str, quinta_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM favorites WHERE user_id = :user_id AND quinta_id = :quinta_id"),
                {"user_id": user_id, "quinta_id": quinta_id},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Favorito no encontrado.")
        return {"message": "Favorito eliminado correctamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
