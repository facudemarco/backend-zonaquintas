"""Administrative endpoints for ZonaQuintas internal backoffice."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from Database.getConnection import engine
from utils.security import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin(user_id: str = Depends(get_current_user)) -> str:
    with engine.connect() as conn:
        role = conn.execute(
            text("SELECT role FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar()

    if (role or "").strip().lower() not in {"admin", "superadmin"}:
        raise HTTPException(403, "Acceso exclusivo para administradores.")
    return user_id


@router.get("/owners/{owner_id}/overview")
async def owner_overview(owner_id: str, _: str = Depends(require_admin)):
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
            SELECT r.*, q.title AS quinta_title, u.name AS guest_name
            FROM reviews r JOIN bookings b ON b.id=r.booking_id
            LEFT JOIN quintas q ON q.id=b.quinta_id
            LEFT JOIN users u ON u.id=b.guest_id
            WHERE b.owner_id=:id ORDER BY r.created_at DESC
        """), {"id": owner_id}).mappings()]
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


@router.get("/dashboard")
async def admin_dashboard(_: str = Depends(require_admin)):
    with engine.connect() as conn:
        users_total = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        owners_total = conn.execute(text(
            "SELECT COUNT(*) FROM users WHERE LOWER(COALESCE(role, '')) = 'owner'"
        )).scalar() or 0
        quintas_total = conn.execute(text("SELECT COUNT(*) FROM quintas")).scalar() or 0
        bookings_total = conn.execute(text("SELECT COUNT(*) FROM bookings")).scalar() or 0
        gross_booking_volume = conn.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM bookings")
        ).scalar() or 0

        quinta_status = conn.execute(text("""
            SELECT COALESCE(status, 'SIN_ESTADO') AS status, COUNT(*) AS total
            FROM quintas GROUP BY COALESCE(status, 'SIN_ESTADO')
        """)).mappings().all()
        booking_status = conn.execute(text("""
            SELECT COALESCE(status, 'SIN_ESTADO') AS status, COUNT(*) AS total
            FROM bookings GROUP BY COALESCE(status, 'SIN_ESTADO')
        """)).mappings().all()
        transaction_status = conn.execute(text("""
            SELECT COALESCE(status, 'SIN_ESTADO') AS status,
                   COUNT(*) AS total, COALESCE(SUM(amount), 0) AS amount
            FROM transactions GROUP BY COALESCE(status, 'SIN_ESTADO')
        """)).mappings().all()
        recent_bookings = conn.execute(text("""
            SELECT b.id, b.quinta_id, b.guest_id, b.owner_id, b.check_in, b.check_out,
                   b.amount, b.currency_price, b.status, b.created_at,
                   COALESCE(q.title, b.quinta_title) AS quinta_title,
                   guest.email AS guest_email, owner.email AS owner_email
            FROM bookings b
            LEFT JOIN quintas q ON q.id = b.quinta_id
            LEFT JOIN users guest ON guest.id = b.guest_id
            LEFT JOIN users owner ON owner.id = b.owner_id
            ORDER BY b.created_at DESC LIMIT 8
        """)).mappings().all()

    return {
        "users": {
            "total": int(users_total),
            "owners": int(owners_total),
            "guests": max(int(users_total) - int(owners_total), 0),
        },
        "quintas": {
            "total": int(quintas_total),
            "by_status": {str(row["status"]): int(row["total"]) for row in quinta_status},
        },
        "bookings": {
            "total": int(bookings_total),
            "by_status": {str(row["status"]): int(row["total"]) for row in booking_status},
            "gross_booking_volume": float(gross_booking_volume),
        },
        "transactions": {
            "by_status": {
                str(row["status"]): {
                    "count": int(row["total"]),
                    "amount": float(row["amount"]),
                } for row in transaction_status
            }
        },
        "recent_bookings": [dict(row) for row in recent_bookings],
        "platform_revenue": None,
        "platform_revenue_note": "No se calcula hasta definir la comisión de ZonaQuintas.",
    }


@router.get("/users")
async def admin_users(
    role: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit, "offset": offset}
    if role:
        clauses.append("LOWER(COALESCE(u.role, '')) = LOWER(:role)")
        params["role"] = role
    if search:
        clauses.append("(u.email LIKE :search OR u.name LIKE :search)")
        params["search"] = f"%{search}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT u.id, u.email, u.name, u.phone, u.date_of_birth, u.address,
                   u.description, u.role, u.owner_time, u.owner_location,
                   u.average_opinions, u.created_at,
                   u.membership_status, u.membership_expires_at,
                   (SELECT COUNT(*) FROM quintas q WHERE q.owner_id = u.id) AS quintas_count,
                   (SELECT COUNT(*) FROM bookings b WHERE b.guest_id = u.id) AS guest_bookings_count,
                   (SELECT COUNT(*) FROM bookings b WHERE b.owner_id = u.id) AS owner_bookings_count
            FROM users u
            {where_sql}
            ORDER BY u.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/bookings")
async def admin_bookings(
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit, "offset": offset}
    if status:
        clauses.append("LOWER(COALESCE(b.status, '')) = LOWER(:status)")
        params["status"] = status
    if search:
        clauses.append("""(
            b.id LIKE :search OR COALESCE(q.title, b.quinta_title, '') LIKE :search
            OR COALESCE(guest.email, '') LIKE :search OR COALESCE(owner.email, '') LIKE :search
        )""")
        params["search"] = f"%{search}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT b.*,
                   COALESCE(q.title, b.quinta_title) AS resolved_quinta_title,
                   q.city AS quinta_city,
                   guest.email AS guest_email, guest.name AS guest_name,
                   owner.email AS owner_email, owner.name AS owner_name,
                   (SELECT COUNT(*) FROM booking_payments bp WHERE bp.booking_id = b.id) AS payment_count
            FROM bookings b
            LEFT JOIN quintas q ON q.id = b.quinta_id
            LEFT JOIN users guest ON guest.id = b.guest_id
            LEFT JOIN users owner ON owner.id = b.owner_id
            {where_sql}
            ORDER BY b.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/quintas")
async def admin_quintas(
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit, "offset": offset}
    if status:
        clauses.append("LOWER(COALESCE(q.status, '')) = LOWER(:status)")
        params["status"] = status
    if search:
        clauses.append("""(
            q.title LIKE :search OR q.city LIKE :search OR q.address LIKE :search
            OR COALESCE(u.email, '') LIKE :search OR COALESCE(u.name, '') LIKE :search
        )""")
        params["search"] = f"%{search}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT q.*, u.email AS owner_email, u.name AS owner_name,
                   u.average_opinions AS owner_average_opinions,
                   (SELECT COUNT(*) FROM bookings b WHERE b.quinta_id = q.id) AS bookings_count,
                   (SELECT COUNT(*) FROM reviews r
                      INNER JOIN bookings rb ON rb.id = r.booking_id
                      WHERE rb.quinta_id = q.id) AS reviews_count
            FROM quintas q
            LEFT JOIN users u ON u.id = q.owner_id
            {where_sql}
            ORDER BY q.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/transactions")
async def admin_transactions(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit, "offset": offset}
    if status:
        clauses.append("LOWER(COALESCE(t.status, '')) = LOWER(:status)")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT t.*, q.title AS quinta_title,
                   owner.email AS owner_email, owner.name AS owner_name,
                   client.email AS client_email, client.name AS client_name
            FROM transactions t
            LEFT JOIN quintas q ON q.id = t.quinta_id
            LEFT JOIN users owner ON owner.id = t.owner_id
            LEFT JOIN users client ON client.id = t.client_id
            {where_sql}
            ORDER BY t.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return [dict(row) for row in rows]
