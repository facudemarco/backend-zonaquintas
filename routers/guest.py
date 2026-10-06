"""Authenticated guest dashboard; no schema changes."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from Database.getConnection import engine
from utils.security import get_current_user
from services.review_eligibility import can_review

router = APIRouter(prefix="/guest", tags=["Guest"])


@router.get("/overview")
async def overview(user_id: str = Depends(get_current_user)):
    with engine.connect() as conn:
        def rows(sql):
            return [dict(r) for r in conn.execute(text(sql), {"id": user_id}).mappings()]

        bookings = rows("""
            SELECT b.*, q.title AS quinta_title, q.address AS quinta_address,
                   q.status AS quinta_status,
                   (SELECT MIN(i.url) FROM quintas_main_images i WHERE i.quinta_id=q.id) AS quinta_main_image
            FROM bookings b LEFT JOIN quintas q ON q.id=b.quinta_id
            WHERE b.guest_id=:id ORDER BY b.created_at DESC
        """)
        payments = rows("""
            SELECT p.id, p.booking_id, p.payment_type, p.amount, p.currency, p.status,
                   p.rebill_payment_link_url, p.payment_expire, p.paid_at
            FROM booking_payments p JOIN bookings b ON b.id=p.booking_id
            WHERE b.guest_id=:id ORDER BY p.created_at DESC
        """)
        reviews = rows("""
            SELECT r.*, q.title AS quinta_title FROM reviews r
            JOIN bookings b ON b.id=r.booking_id LEFT JOIN quintas q ON q.id=b.quinta_id
            WHERE b.guest_id=:id ORDER BY r.created_at DESC
        """)
        favorites = rows("""
            SELECT q.id, q.title, q.city, q.price, q.currency_price,
                   (SELECT MIN(i.url) FROM quintas_main_images i WHERE i.quinta_id=q.id) AS main_image
            FROM quintas q WHERE LOWER(q.status)='active' AND EXISTS
                (SELECT 1 FROM favorites f WHERE f.quinta_id=q.id AND f.user_id=:id)
            ORDER BY q.title
        """)
    reviewed = {r["booking_id"] for r in reviews}
    for booking in bookings:
        booking["payments"] = [p for p in payments if p["booking_id"] == booking["id"]]
        booking["can_review"] = booking["id"] not in reviewed and can_review(booking)
    return {"bookings": bookings, "favorites": favorites, "reviews": reviews}
