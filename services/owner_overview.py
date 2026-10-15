"""Shared owner data, scoped to a single authenticated account by callers."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import text
from services.review_eligibility import utc_now, review_eligibility

def build_owner_overview(engine, owner_id: str):
    now = utc_now()
    with engine.connect() as conn:
        owner = conn.execute(text("""
            SELECT id, name, email, phone, address, description, created_at,
                   owner_location, average_opinions
            FROM users WHERE id = :id
        """), {"id": owner_id}).mappings().first()
        if owner is None:
            raise HTTPException(404, "Cliente no encontrado.")
        profile = dict(owner)
        profile["pictures"] = [dict(row) for row in conn.execute(text(
            "SELECT id, url FROM users_picture WHERE user_id = :id"
        ), {"id": owner_id}).mappings()]

        properties = [dict(row) for row in conn.execute(text("""
            SELECT q.id, q.title, q.address, q.city, q.status, q.price,
                   q.currency_price, q.guests, q.bedrooms, q.bathrooms,
                   q.rental_start_date, q.rental_end_date, q.created_at,
                   (SELECT MIN(i.url) FROM quintas_main_images i WHERE i.quinta_id = q.id) AS main_image
            FROM quintas q WHERE q.owner_id = :id ORDER BY q.created_at DESC
        """), {"id": owner_id}).mappings()]
        bookings = [dict(row) for row in conn.execute(text("""
            SELECT b.*, q.title AS quinta_title, u.name AS guest_name,
                   u.email AS guest_email, u.phone AS guest_phone
            FROM bookings b LEFT JOIN quintas q ON q.id = b.quinta_id
            LEFT JOIN users u ON u.id = b.guest_id
            WHERE b.owner_id = :id ORDER BY b.created_at DESC
        """), {"id": owner_id}).mappings()]
        payments = [dict(row) for row in conn.execute(text("""
            SELECT p.id, p.booking_id, p.payment_type, p.amount, p.currency,
                   p.status, p.created_at, p.paid_at
            FROM booking_payments p JOIN bookings b ON b.id = p.booking_id
            WHERE b.owner_id = :id ORDER BY p.created_at DESC
        """), {"id": owner_id}).mappings()]
        reviews = [dict(row) for row in conn.execute(text("""
            SELECT r.*, b.quinta_id, q.title AS quinta_title, u.name AS guest_name
            FROM reviews r JOIN bookings b ON b.id=r.booking_id
            LEFT JOIN quintas q ON q.id=b.quinta_id
            LEFT JOIN users u ON u.id=b.guest_id
            WHERE r.recipient_id=:id AND r.direction='guest_to_owner'
              AND r.moderation_status='visible' AND r.reveal_at <= :now
            ORDER BY r.created_at DESC
        """), {"id": owner_id, "now": now}).mappings()]
        profile["average_opinions"] = (sum(float(row["stars"]) for row in reviews) / len(reviews)) if reviews else None
        authored = set(conn.execute(text(
            "SELECT booking_id FROM reviews WHERE author_id=:id AND direction='owner_to_guest'"
        ), {"id": owner_id}).scalars())
        for booking in bookings:
            booking["can_review"] = review_eligibility(booking, owner_id, booking["id"] in authored, now) is None
        transactions = [dict(row) for row in conn.execute(text("""
            SELECT t.id, t.booking_id, t.amount, t.currency, t.status,
                   t.created_at AS date, t.description, t.transfer_date_estimate,
                   q.title AS quinta_name
            FROM transactions t LEFT JOIN quintas q ON q.id = t.quinta_id
            WHERE t.owner_id = :id ORDER BY t.created_at DESC
        """), {"id": owner_id}).mappings()]

    balances = {status: {"ARS": Decimal(0), "USD": Decimal(0)}
                for status in ("retenido", "disponible", "entregado")}
    for tx in transactions:
        status = (tx["status"] or "").lower()
        currency = tx["currency"]
        if status in balances and currency in balances[status]:
            balances[status][currency] += Decimal(str(tx["amount"] or 0))
    return {"owner": profile, "properties": properties, "bookings": bookings,
            "reviews": reviews, "payments": payments, "balances": balances, "transactions": transactions}

