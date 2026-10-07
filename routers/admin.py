"""Administrative endpoints for ZonaQuintas internal backoffice."""
from decimal import Decimal
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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


class AdminStatusUpdate(BaseModel):
    status: str


@router.get("/bookings/{booking_id}")
async def admin_booking_detail(booking_id: str, _: str = Depends(require_admin)):
    with engine.connect() as conn:
        booking = conn.execute(text("""
            SELECT b.*,
                   COALESCE(q.title, b.quinta_title) AS resolved_quinta_title,
                   q.city AS quinta_city,
                   guest.name AS guest_name, guest.email AS guest_email, guest.phone AS guest_phone,
                   owner.name AS owner_name, owner.email AS owner_email, owner.phone AS owner_phone
            FROM bookings b
            LEFT JOIN quintas q ON q.id = b.quinta_id
            LEFT JOIN users guest ON guest.id = b.guest_id
            LEFT JOIN users owner ON owner.id = b.owner_id
            WHERE b.id = :id
        """), {"id": booking_id}).mappings().first()
        if not booking:
            raise HTTPException(404, "Reserva no encontrada.")

        payments = [dict(row) for row in conn.execute(text("""
            SELECT * FROM booking_payments
            WHERE booking_id = :id
            ORDER BY created_at DESC
        """), {"id": booking_id}).mappings()]

        transactions = [dict(row) for row in conn.execute(text("""
            SELECT * FROM transactions
            WHERE booking_id = :id
            ORDER BY created_at DESC
        """), {"id": booking_id}).mappings()]

    return {
        "booking": dict(booking),
        "payments": payments,
        "transactions": transactions,
    }


@router.patch("/bookings/{booking_id}/status")
async def admin_booking_status(
    booking_id: str,
    data: AdminStatusUpdate,
    _: str = Depends(require_admin),
):
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE bookings SET status = :status, updated_at = NOW() WHERE id = :id"),
            {"status": data.status, "id": booking_id},
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Reserva no encontrada.")
    return {"message": "Estado de reserva actualizado.", "status": data.status}


@router.get("/quintas/{quinta_id}")
async def admin_quinta_detail(quinta_id: str, _: str = Depends(require_admin)):
    with engine.connect() as conn:
        quinta = conn.execute(text("""
            SELECT q.*,
                   u.name AS owner_name, u.email AS owner_email, u.phone AS owner_phone,
                   u.average_opinions AS owner_average_opinions
            FROM quintas q
            LEFT JOIN users u ON u.id = q.owner_id
            WHERE q.id = :id
        """), {"id": quinta_id}).mappings().first()
        if not quinta:
            raise HTTPException(404, "Quinta no encontrada.")

        main_image = conn.execute(
            text("SELECT url FROM quintas_main_images WHERE quinta_id = :id"),
            {"id": quinta_id},
        ).scalar()

        images = conn.execute(
            text("SELECT url FROM images_quintas WHERE quinta_id = :id"),
            {"id": quinta_id},
        ).scalars().all()

        bookings = [dict(row) for row in conn.execute(text("""
            SELECT b.id, b.guest_id, b.check_in, b.check_out, b.amount,
                   b.currency_price, b.status, b.created_at,
                   u.name AS guest_name, u.email AS guest_email
            FROM bookings b
            LEFT JOIN users u ON u.id = b.guest_id
            WHERE b.quinta_id = :id
            ORDER BY b.created_at DESC
            LIMIT 30
        """), {"id": quinta_id}).mappings()]

        reviews = [dict(row) for row in conn.execute(text("""
            SELECT r.*, b.guest_id, u.name AS guest_name
            FROM reviews r
            JOIN bookings b ON b.id = r.booking_id
            LEFT JOIN users u ON u.id = b.guest_id
            WHERE b.quinta_id = :id
            ORDER BY r.created_at DESC
        """), {"id": quinta_id}).mappings()]

    return {
        "quinta": dict(quinta),
        "main_image": main_image,
        "images": list(images),
        "bookings": bookings,
        "reviews": reviews,
    }


@router.patch("/quintas/{quinta_id}/status")
async def admin_quinta_status(
    quinta_id: str,
    data: AdminStatusUpdate,
    _: str = Depends(require_admin),
):
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE quintas SET status = :status WHERE id = :id"),
            {"status": data.status, "id": quinta_id},
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Quinta no encontrada.")
    return {"message": "Estado de quinta actualizado.", "status": data.status}


@router.get("/users/{user_id}")
async def admin_user_detail(user_id: str, _: str = Depends(require_admin)):
    with engine.connect() as conn:
        user = conn.execute(text("""
            SELECT id, email, name, phone, date_of_birth, address, description, role,
                   owner_time, owner_location, average_opinions, created_at,
                   membership_status, membership_expires_at
            FROM users
            WHERE id = :id
        """), {"id": user_id}).mappings().first()
        if not user:
            raise HTTPException(404, "Usuario no encontrado.")

        pictures = [dict(row) for row in conn.execute(
            text("SELECT id, url FROM users_picture WHERE user_id = :id"),
            {"id": user_id},
        ).mappings()]

        quintas = [dict(row) for row in conn.execute(text("""
            SELECT id, title, city, status, price, currency_price, created_at
            FROM quintas WHERE owner_id = :id
            ORDER BY created_at DESC
        """), {"id": user_id}).mappings()]

        guest_bookings = [dict(row) for row in conn.execute(text("""
            SELECT b.id, b.quinta_id, b.check_in, b.check_out, b.amount,
                   b.currency_price, b.status, b.created_at,
                   COALESCE(q.title, b.quinta_title) AS quinta_title
            FROM bookings b
            LEFT JOIN quintas q ON q.id = b.quinta_id
            WHERE b.guest_id = :id
            ORDER BY b.created_at DESC
            LIMIT 30
        """), {"id": user_id}).mappings()]

        owner_bookings = [dict(row) for row in conn.execute(text("""
            SELECT b.id, b.quinta_id, b.check_in, b.check_out, b.amount,
                   b.currency_price, b.status, b.created_at,
                   COALESCE(q.title, b.quinta_title) AS quinta_title,
                   guest.name AS guest_name, guest.email AS guest_email
            FROM bookings b
            LEFT JOIN quintas q ON q.id = b.quinta_id
            LEFT JOIN users guest ON guest.id = b.guest_id
            WHERE b.owner_id = :id
            ORDER BY b.created_at DESC
            LIMIT 30
        """), {"id": user_id}).mappings()]

        reviews = [dict(row) for row in conn.execute(text("""
            SELECT r.*, b.quinta_id, q.title AS quinta_title
            FROM reviews r
            JOIN bookings b ON b.id = r.booking_id
            LEFT JOIN quintas q ON q.id = b.quinta_id
            WHERE b.guest_id = :id OR b.owner_id = :id
            ORDER BY r.created_at DESC
            LIMIT 30
        """), {"id": user_id}).mappings()]

    return {
        "user": dict(user),
        "pictures": pictures,
        "quintas": quintas,
        "guest_bookings": guest_bookings,
        "owner_bookings": owner_bookings,
        "reviews": reviews,
    }


class QuintaVerificationUpdate(BaseModel):
    status: str
    rejection_reason: Optional[str] = None
    admin_notes: Optional[str] = None


@router.get("/verifications")
async def admin_verifications(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit, "offset": offset}
    if status:
        clauses.append("LOWER(COALESCE(v.status, 'PENDIENTE')) = LOWER(:status)")
        params["status"] = status
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT q.id AS quinta_id, q.title, q.city, q.address, q.status AS quinta_status,
                   q.owner_id, u.name AS owner_name, u.email AS owner_email,
                   COALESCE(v.status, 'PENDIENTE') AS verification_status,
                   v.rejection_reason, v.admin_notes, v.verified_by, v.verified_at, v.updated_at
            FROM quintas q
            LEFT JOIN users u ON u.id = q.owner_id
            LEFT JOIN quinta_verifications v ON v.quinta_id = q.id
            {where_sql}
            ORDER BY
              CASE COALESCE(v.status, 'PENDIENTE')
                WHEN 'PENDIENTE' THEN 0
                WHEN 'EN_REVISION' THEN 1
                WHEN 'RECHAZADA' THEN 2
                WHEN 'VERIFICADA' THEN 3
                ELSE 4
              END,
              q.created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/verifications/{quinta_id}")
async def admin_verification_detail(quinta_id: str, _: str = Depends(require_admin)):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT q.*, u.name AS owner_name, u.email AS owner_email, u.phone AS owner_phone,
                   COALESCE(v.status, 'PENDIENTE') AS verification_status,
                   v.rejection_reason, v.admin_notes, v.verified_by, v.verified_at, v.updated_at
            FROM quintas q
            LEFT JOIN users u ON u.id = q.owner_id
            LEFT JOIN quinta_verifications v ON v.quinta_id = q.id
            WHERE q.id = :id
        """), {"id": quinta_id}).mappings().first()
        if not row:
            raise HTTPException(404, "Quinta no encontrada.")

        events = [dict(event) for event in conn.execute(text("""
            SELECT e.*, u.name AS admin_name, u.email AS admin_email
            FROM admin_moderation_events e
            LEFT JOIN users u ON u.id = e.admin_id
            WHERE e.entity_type = 'quinta' AND e.entity_id = :id
            ORDER BY e.created_at DESC
        """), {"id": quinta_id}).mappings()]

    return {"quinta": dict(row), "moderation_events": events}


@router.patch("/verifications/{quinta_id}")
async def admin_update_verification(
    quinta_id: str,
    data: QuintaVerificationUpdate,
    admin_id: str = Depends(require_admin),
):
    allowed = {"PENDIENTE", "EN_REVISION", "VERIFICADA", "RECHAZADA"}
    new_status = data.status.strip().upper()
    if new_status not in allowed:
        raise HTTPException(422, "Estado de verificación inválido.")
    if new_status == "RECHAZADA" and not (data.rejection_reason or "").strip():
        raise HTTPException(422, "El motivo de rechazo es obligatorio.")

    with engine.begin() as conn:
        if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": quinta_id}).fetchone():
            raise HTTPException(404, "Quinta no encontrada.")

        previous = conn.execute(
            text("SELECT status FROM quinta_verifications WHERE quinta_id = :id"),
            {"id": quinta_id},
        ).scalar() or "PENDIENTE"

        verified_at_sql = "NOW()" if new_status == "VERIFICADA" else "NULL"
        conn.execute(text(f"""
            INSERT INTO quinta_verifications
                (quinta_id, status, rejection_reason, admin_notes, verified_by, verified_at, created_at, updated_at)
            VALUES
                (:quinta_id, :status, :rejection_reason, :admin_notes, :verified_by, {verified_at_sql}, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                rejection_reason = VALUES(rejection_reason),
                admin_notes = VALUES(admin_notes),
                verified_by = VALUES(verified_by),
                verified_at = {verified_at_sql},
                updated_at = NOW()
        """), {
            "quinta_id": quinta_id,
            "status": new_status,
            "rejection_reason": data.rejection_reason,
            "admin_notes": data.admin_notes,
            "verified_by": admin_id,
        })

        conn.execute(text("""
            INSERT INTO admin_moderation_events
                (id, entity_type, entity_id, action, previous_status, new_status, reason, admin_id, created_at)
            VALUES
                (:id, 'quinta', :entity_id, 'VERIFICATION_STATUS_CHANGED',
                 :previous_status, :new_status, :reason, :admin_id, NOW())
        """), {
            "id": str(uuid.uuid4()),
            "entity_id": quinta_id,
            "previous_status": previous,
            "new_status": new_status,
            "reason": data.rejection_reason or data.admin_notes,
            "admin_id": admin_id,
        })

    return {"message": "Verificación actualizada.", "status": new_status}


@router.get("/moderation-events")
async def admin_moderation_events(
    entity_type: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    _: str = Depends(require_admin),
):
    clauses = []
    params = {"limit": limit}
    if entity_type:
        clauses.append("e.entity_type = :entity_type")
        params["entity_type"] = entity_type
    if entity_id:
        clauses.append("e.entity_id = :entity_id")
        params["entity_id"] = entity_id
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT e.*, u.name AS admin_name, u.email AS admin_email
            FROM admin_moderation_events e
            LEFT JOIN users u ON u.id = e.admin_id
            {where_sql}
            ORDER BY e.created_at DESC
            LIMIT :limit
        """), params).mappings().all()
    return [dict(row) for row in rows]
