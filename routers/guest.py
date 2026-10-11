"""Authenticated guest dashboard; no schema changes."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from Database.getConnection import engine
from utils.security import get_current_user
from services.review_eligibility import review_eligibility, review_window, utc_now

router = APIRouter(prefix="/guest", tags=["Guest"])


@router.get("/overview")
async def overview(user_id: str = Depends(get_current_user)):
    now = utc_now()
    with engine.connect() as conn:
        def rows(sql):
            return [dict(r) for r in conn.execute(text(sql), {"id": user_id, "now": now}).mappings()]

        bookings = rows("""
            SELECT b.*, q.title AS quinta_title, q.address AS quinta_address,
                   q.status AS quinta_status,
                   u.name AS owner_name,
                   (SELECT MIN(p.url) FROM users_picture p WHERE p.user_id=b.owner_id) AS owner_avatar_url,
                   (SELECT MIN(i.url) FROM quintas_main_images i WHERE i.quinta_id=q.id) AS quinta_main_image
            FROM bookings b LEFT JOIN quintas q ON q.id=b.quinta_id
            LEFT JOIN users u ON u.id=b.owner_id
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
            WHERE r.author_id=:id AND r.direction='guest_to_owner' ORDER BY r.created_at DESC
        """)
        received_reviews = rows("""
            SELECT r.*, q.title AS quinta_title FROM reviews r
            JOIN bookings b ON b.id=r.booking_id LEFT JOIN quintas q ON q.id=b.quinta_id
            WHERE r.recipient_id=:id AND r.direction='owner_to_guest'
              AND r.moderation_status='visible' AND r.reveal_at <= :now
            ORDER BY r.created_at DESC
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
        reason = review_eligibility(booking, user_id, booking["id"] in reviewed, now)
        window = review_window(booking)
        booking["can_review"] = reason is None
        booking["review_reason"] = reason
        booking["review_opens_at"] = window[0] if window else None
        booking["review_deadline_at"] = window[1] if window else None
    return {"bookings": bookings, "favorites": favorites, "reviews": reviews, "received_reviews": received_reviews}
