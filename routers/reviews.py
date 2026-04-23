import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from Database.getConnection import engine
from models.reviews import ReviewCreate

router = APIRouter()

REVIEWABLE_STATUSES = {"COMPLETADO", "FINALIZADO", "COMPLETED", "FINISHED"}


@router.post("/reviews", tags=["Reviews"])
async def create_review(data: ReviewCreate):
    try:
        review_id = str(uuid.uuid4())
        with engine.begin() as conn:
            booking = conn.execute(
                text("SELECT id, owner_id, status FROM bookings WHERE id = :id"),
                {"id": data.booking_id},
            ).fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Reserva no encontrada.")
            if booking.status and booking.status.upper() not in REVIEWABLE_STATUSES:
                raise HTTPException(status_code=409, detail="La reserva todavia no esta finalizada.")

            existing = conn.execute(
                text("SELECT id FROM reviews WHERE booking_id = :booking_id"),
                {"booking_id": data.booking_id},
            ).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="La reserva ya tiene una review.")

            conn.execute(
                text("""
                    INSERT INTO reviews (id, booking_id, stars, review_text, created_at)
                    VALUES (:id, :booking_id, :stars, :review_text, NOW())
                """),
                {
                    "id": review_id,
                    "booking_id": data.booking_id,
                    "stars": data.stars,
                    "review_text": data.review_text,
                },
            )

            avg = conn.execute(
                text("""
                    SELECT AVG(r.stars) AS average_stars
                    FROM reviews r
                    INNER JOIN bookings b ON r.booking_id = b.id
                    WHERE b.owner_id = :owner_id
                """),
                {"owner_id": booking.owner_id},
            ).fetchone()
            if avg and avg.average_stars is not None:
                conn.execute(
                    text("UPDATE users SET average_opinions = :avg WHERE id = :id"),
                    {"avg": float(avg.average_stars), "id": booking.owner_id},
                )
        return {"message": "Review creada correctamente.", "id": review_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reviews/quinta/{quinta_id}", tags=["Reviews"])
async def get_quinta_reviews(quinta_id: str):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT r.*, b.quinta_id, b.guest_id, u.email AS guest_email
                    FROM reviews r
                    INNER JOIN bookings b ON r.booking_id = b.id
                    LEFT JOIN users u ON b.guest_id = u.id
                    WHERE b.quinta_id = :quinta_id
                    ORDER BY r.created_at DESC
                """),
                {"quinta_id": quinta_id},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reviews/user/{user_id}", tags=["Reviews"])
async def get_user_reviews(user_id: str):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT r.*, b.quinta_id, b.guest_id, b.owner_id, q.title AS quinta_title
                    FROM reviews r
                    INNER JOIN bookings b ON r.booking_id = b.id
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    WHERE b.guest_id = :user_id OR b.owner_id = :user_id
                    ORDER BY r.created_at DESC
                """),
                {"user_id": user_id},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
