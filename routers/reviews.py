"""Verified, bilateral reviews tied to completed bookings."""

import os
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from Database.getConnection import engine
from models.reviews import ReviewCreate, ReviewModeration, ReviewReportCreate
from services.review_eligibility import review_eligibility, review_window, utc_now
from utils.security import get_current_user

router = APIRouter(tags=["Reviews"])


def require_admin(user_id: str = Depends(get_current_user)) -> str:
    with engine.connect() as conn:
        role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).scalar()
    if (role or "").lower() not in {"admin", "superadmin"}:
        raise HTTPException(403, "Acceso exclusivo para administradores.")
    return user_id

VISIBLE = "r.moderation_status = 'visible' AND r.reveal_at <= :now"
REVIEW_SELECT = """
    SELECT r.id, r.booking_id, r.author_id, r.recipient_id, r.direction,
           r.stars, r.review_text, r.created_at, r.reveal_at, r.moderation_status,
           b.quinta_id, q.title AS quinta_title, u.name AS author_full_name,
           (SELECT MIN(p.url) FROM users_picture p WHERE p.user_id = r.author_id) AS author_avatar_url
    FROM reviews r JOIN bookings b ON b.id = r.booking_id
    LEFT JOIN quintas q ON q.id = b.quinta_id
    JOIN users u ON u.id = r.author_id
"""


def _display(row):
    item = dict(row)
    full_name = (item.pop("author_full_name", None) or "").strip()
    item["author_name"] = full_name.split()[0] if full_name else "Usuario"
    return item


def _as_datetime(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _summary(conn, where: str, params: dict):
    row = conn.execute(text(f"""
        SELECT COUNT(*) AS count, AVG(r.stars) AS average,
               SUM(CASE WHEN r.stars = 1 THEN 1 ELSE 0 END) AS one,
               SUM(CASE WHEN r.stars = 2 THEN 1 ELSE 0 END) AS two,
               SUM(CASE WHEN r.stars = 3 THEN 1 ELSE 0 END) AS three,
               SUM(CASE WHEN r.stars = 4 THEN 1 ELSE 0 END) AS four,
               SUM(CASE WHEN r.stars = 5 THEN 1 ELSE 0 END) AS five
        FROM reviews r JOIN bookings b ON b.id = r.booking_id
        WHERE {VISIBLE} AND {where}
    """), params).mappings().one()
    return {"count": row["count"], "average": float(row["average"]) if row["average"] is not None else None,
            "distribution": {str(i): int(row[k] or 0) for i, k in enumerate(("one", "two", "three", "four", "five"), 1)}}


def _sync_host_average(conn, recipient_id: str, now: datetime):
    average = conn.execute(text(f"""
        SELECT AVG(r.stars) FROM reviews r
        WHERE r.recipient_id = :id AND r.direction = 'guest_to_owner' AND {VISIBLE}
    """), {"id": recipient_id, "now": now}).scalar()
    conn.execute(text("UPDATE users SET average_opinions = :average WHERE id = :id"),
                 {"average": average, "id": recipient_id})


def _booking_review_state(conn, booking_id: str, user_id: str, now: datetime):
    booking = conn.execute(text("""
        SELECT id, quinta_id, guest_id, owner_id, status, check_in, check_out,
               quinta_title FROM bookings WHERE id = :id
    """), {"id": booking_id}).mappings().first()
    if booking is None:
        raise HTTPException(404, "Reserva no encontrada.")
    booking = dict(booking)
    if user_id not in (booking["guest_id"], booking["owner_id"]):
        raise HTTPException(403, "No participás en esta reserva.")
    rows = conn.execute(text(REVIEW_SELECT + " WHERE r.booking_id = :id ORDER BY r.created_at, r.id"),
                        {"id": booking_id}).mappings().all()
    own = next((_display(row) for row in rows if row["author_id"] == user_id), None)
    received = next((_display(row) for row in rows if row["recipient_id"] == user_id
                     and row["moderation_status"] == "visible" and _as_datetime(row["reveal_at"]) <= now), None)
    reason = review_eligibility(booking, user_id, own is not None, now)
    window = review_window(booking)
    recipient_id = booking["owner_id"] if user_id == booking["guest_id"] else booking["guest_id"]
    recipient = conn.execute(text("""
        SELECT name, (SELECT MIN(url) FROM users_picture WHERE user_id = :id) AS avatar_url
        FROM users WHERE id = :id
    """), {"id": recipient_id}).mappings().first()
    recipient_name = ((recipient["name"] if recipient else None) or "").strip().split()
    return {"booking_id": booking_id, "quinta_title": booking["quinta_title"],
            "check_in": booking["check_in"], "check_out": booking["check_out"],
            "recipient_id": recipient_id, "recipient_name": recipient_name[0] if recipient_name else "Usuario",
            "recipient_avatar_url": recipient["avatar_url"] if recipient else None,
            "direction": "guest_to_owner" if user_id == booking["guest_id"] else "owner_to_guest",
            "can_review": reason is None, "review_reason": reason,
            "review_opens_at": window[0] if window else None, "review_deadline_at": window[1] if window else None,
            "written": own, "received": received}


@router.get("/reviews/booking/{booking_id}")
def booking_reviews(booking_id: str, user_id: str = Depends(get_current_user)):
    with engine.connect() as conn:
        return _booking_review_state(conn, booking_id, user_id, utc_now())


@router.post("/reviews", status_code=201)
def create_review(data: ReviewCreate, user_id: str = Depends(get_current_user)):
    review_id = str(uuid.uuid4())
    now = utc_now()
    try:
        with engine.begin() as conn:
            suffix = " FOR UPDATE" if conn.dialect.name == "mysql" else ""
            booking = conn.execute(text("""
                SELECT id, guest_id, owner_id, check_out, status
                FROM bookings WHERE id = :id
            """ + suffix), {"id": data.booking_id}).mappings().first()
            if booking is None:
                raise HTTPException(404, "Reserva no encontrada.")
            booking = dict(booking)
            if user_id not in (booking["guest_id"], booking["owner_id"]):
                raise HTTPException(403, "No participás en esta reserva.")
            existing = conn.execute(text("SELECT id FROM reviews WHERE booking_id = :id AND author_id = :author"),
                                    {"id": data.booking_id, "author": user_id}).first()
            reason = review_eligibility(booking, user_id, existing is not None, now)
            if reason:
                raise HTTPException(409, reason)
            direction = "guest_to_owner" if user_id == booking["guest_id"] else "owner_to_guest"
            recipient_id = booking["owner_id"] if direction == "guest_to_owner" else booking["guest_id"]
            deadline = review_window(booking)[1]
            conn.execute(text("""
                INSERT INTO reviews (id, booking_id, author_id, recipient_id, direction,
                                     stars, review_text, created_at, reveal_at, moderation_status)
                VALUES (:id, :booking_id, :author_id, :recipient_id, :direction,
                        :stars, :review_text, :created_at, :reveal_at, 'visible')
            """), {"id": review_id, "booking_id": data.booking_id, "author_id": user_id,
                   "recipient_id": recipient_id, "direction": direction, "stars": data.stars,
                   "review_text": data.review_text, "created_at": now, "reveal_at": deadline})
            total = conn.execute(text("SELECT COUNT(*) FROM reviews WHERE booking_id = :id"),
                                 {"id": data.booking_id}).scalar()
            if total == 2:
                conn.execute(text("UPDATE reviews SET reveal_at = :now WHERE booking_id = :id"),
                             {"now": now, "id": data.booking_id})
                _sync_host_average(conn, booking["owner_id"], now)
            conn.execute(text("""
                UPDATE review_reminders SET status = 'cancelled', lease_until = NULL
                WHERE booking_id = :booking_id AND user_id = :user_id AND status IN ('pending', 'leased')
            """), {"booking_id": data.booking_id, "user_id": user_id})
        return {"id": review_id, "status": "visible" if total == 2 else "awaiting_reveal", "reveal_at": now if total == 2 else deadline}
    except IntegrityError:
        raise HTTPException(409, "Ya enviaste una reseña para esta reserva.")


@router.get("/quintas/{quinta_id}/reviews")
def quinta_reviews(quinta_id: str, limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0),
                   stars: int | None = Query(None, ge=1, le=5)):
    now = utc_now()
    with engine.connect() as conn:
        quinta = conn.execute(text("SELECT id FROM quintas WHERE id = :id AND LOWER(status) = 'active'"),
                              {"id": quinta_id}).first()
        if quinta is None:
            raise HTTPException(404, "Quinta no encontrada.")
        params = {"quinta_id": quinta_id, "now": now, "limit": limit, "offset": offset, "stars": stars}
        where = "b.quinta_id = :quinta_id AND r.direction = 'guest_to_owner'"
        summary = _summary(conn, where, params)
        filtered = where + (" AND r.stars = :stars" if stars is not None else "")
        total = conn.execute(text(f"SELECT COUNT(*) FROM reviews r JOIN bookings b ON b.id=r.booking_id WHERE {VISIBLE} AND {filtered}"), params).scalar()
        rows = conn.execute(text(REVIEW_SELECT + f" WHERE {VISIBLE} AND {filtered} ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
    items = [{k: v for k, v in _display(row).items() if k in {"id", "stars", "review_text", "created_at", "author_name", "author_avatar_url"}} for row in rows]
    return {"items": items, "summary": summary, "total_matching": total, "limit": limit, "offset": offset}


@router.get("/reviews/quinta/{quinta_id}")
def legacy_quinta_reviews(quinta_id: str, limit: int = Query(10, ge=1, le=50), offset: int = Query(0, ge=0),
                         stars: int | None = Query(None, ge=1, le=5)):
    return quinta_reviews(quinta_id, limit, offset, stars)


@router.get("/reviews/me")
def my_reviews(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
               quinta_id: str | None = Query(None),
               user_id: str = Depends(get_current_user)):
    now = utc_now()
    with engine.connect() as conn:
        rows = conn.execute(text(REVIEW_SELECT + """
            WHERE (r.author_id = :id OR (r.recipient_id = :id AND """ + VISIBLE + """ ))
              AND (:quinta_id IS NULL OR b.quinta_id = :quinta_id)
            ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset
        """), {"id": user_id, "now": now, "limit": limit, "offset": offset, "quinta_id": quinta_id}).mappings().all()
        host = _summary(conn, "r.recipient_id = :id AND r.direction = 'guest_to_owner'", {"id": user_id, "now": now})
        guest = _summary(conn, "r.recipient_id = :id AND r.direction = 'owner_to_guest'", {"id": user_id, "now": now})
    items = [_display(row) for row in rows]
    return {"items": items, "host_summary": host, "guest_summary": guest, "limit": limit, "offset": offset}


@router.get("/reviews/user/{user_id}")
def user_reviews(user_id: str, viewer_id: str = Depends(get_current_user)):
    if viewer_id != user_id:
        with engine.connect() as conn:
            role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": viewer_id}).scalar()
        if (role or "").lower() not in {"admin", "superadmin"}:
            raise HTTPException(403, "No podés consultar las reseñas de otro usuario.")
    return my_reviews(limit=20, offset=0, quinta_id=None, user_id=user_id)


@router.get("/reviews/host/{owner_id}/summary")
def host_summary(owner_id: str):
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": owner_id}).first()
        if not exists:
            raise HTTPException(404, "Anfitrión no encontrado.")
        return _summary(conn, "r.recipient_id = :id AND r.direction = 'guest_to_owner'",
                        {"id": owner_id, "now": utc_now()})


@router.get("/reviews/guest/{guest_id}/summary")
def guest_summary(guest_id: str, user_id: str = Depends(get_current_user)):
    with engine.connect() as conn:
        if user_id != guest_id:
            role = conn.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).scalar()
            related = conn.execute(text("""
                SELECT id FROM bookings WHERE owner_id = :owner_id AND guest_id = :guest_id LIMIT 1
            """), {"owner_id": user_id, "guest_id": guest_id}).first()
            if (role or "").lower() not in {"admin", "superadmin"} and not related:
                raise HTTPException(403, "No podés consultar esta reputación.")
        return _summary(conn, "r.recipient_id = :id AND r.direction = 'owner_to_guest'",
                        {"id": guest_id, "now": utc_now()})


@router.post("/reviews/{review_id}/reports", status_code=201)
def report_review(review_id: str, data: ReviewReportCreate, user_id: str = Depends(get_current_user)):
    now = utc_now()
    try:
        with engine.begin() as conn:
            row = conn.execute(text("""
                SELECT r.id, r.author_id, r.recipient_id, r.direction,
                       r.moderation_status, r.reveal_at, q.status AS quinta_status
                FROM reviews r JOIN bookings b ON b.id=r.booking_id
                JOIN quintas q ON q.id=b.quinta_id WHERE r.id = :id
            """), {"id": review_id}).mappings().first()
            if not row or row["moderation_status"] != "visible" or _as_datetime(row["reveal_at"]) > now:
                raise HTTPException(404, "Reseña no disponible.")
            if row["direction"] == "owner_to_guest" and user_id not in (row["author_id"], row["recipient_id"]):
                raise HTTPException(403, "No podés denunciar esta reseña.")
            if row["direction"] == "guest_to_owner" and (row["quinta_status"] or "").lower() != "active" and user_id != row["recipient_id"]:
                raise HTTPException(403, "No podés denunciar esta reseña.")
            if user_id == row["author_id"]:
                raise HTTPException(403, "No podés denunciar tu propia reseña.")
            conn.execute(text("""
                INSERT INTO review_reports (id, review_id, reporter_id, reason, detail, status, created_at)
                VALUES (:id, :review_id, :reporter_id, :reason, :detail, 'open', :created_at)
            """), {"id": str(uuid.uuid4()), "review_id": review_id, "reporter_id": user_id,
                   "reason": data.reason, "detail": data.detail, "created_at": now})
        return {"message": "Denuncia recibida."}
    except IntegrityError:
        raise HTTPException(409, "Ya denunciaste esta reseña.")


@router.get("/admin/reviews")
def admin_reviews(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
                  _: str = Depends(require_admin)):
    with engine.connect() as conn:
        rows = conn.execute(text(REVIEW_SELECT + " ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset"),
                            {"limit": limit, "offset": offset}).mappings().all()
        reports = conn.execute(text("""
            SELECT id, review_id, reporter_id, reason, detail, status, created_at, resolved_at
            FROM review_reports ORDER BY created_at DESC LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset}).mappings().all()
    return {"items": [_display(row) for row in rows], "reports": [dict(row) for row in reports]}


@router.patch("/admin/reviews/{review_id}/moderation")
def moderate_review(review_id: str, data: ReviewModeration, admin_id: str = Depends(require_admin)):
    if data.action not in {"hide", "restore"}:
        raise HTTPException(422, "Acción inválida.")
    new_status = "hidden" if data.action == "hide" else "visible"
    now = utc_now()
    with engine.begin() as conn:
        suffix = " FOR UPDATE" if conn.dialect.name == "mysql" else ""
        row = conn.execute(text("SELECT recipient_id, direction, moderation_status FROM reviews WHERE id = :id" + suffix),
                           {"id": review_id}).mappings().first()
        if row is None:
            raise HTTPException(404, "Reseña no encontrada.")
        if row["moderation_status"] == new_status:
            raise HTTPException(409, "La reseña ya tiene ese estado.")
        conn.execute(text("UPDATE reviews SET moderation_status = :status WHERE id = :id"),
                     {"status": new_status, "id": review_id})
        conn.execute(text("""
            INSERT INTO review_moderation_events
            (id, review_id, admin_id, action, old_status, new_status, reason, created_at)
            VALUES (:id, :review_id, :admin_id, :action, :old_status, :new_status, :reason, :created_at)
        """), {"id": str(uuid.uuid4()), "review_id": review_id, "admin_id": admin_id,
               "action": data.action, "old_status": row["moderation_status"],
               "new_status": new_status, "reason": data.reason, "created_at": now})
        conn.execute(text("UPDATE review_reports SET status = 'resolved', resolved_at = :now WHERE review_id = :id AND status = 'open'"),
                     {"id": review_id, "now": now})
        if row["direction"] == "guest_to_owner":
            _sync_host_average(conn, row["recipient_id"], now)
    return {"status": new_status}


@router.get("/admin/reviews/{review_id}/moderation-events")
def review_moderation_events(review_id: str, _: str = Depends(require_admin)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, admin_id, action, old_status, new_status, reason, created_at
            FROM review_moderation_events WHERE review_id = :id ORDER BY created_at DESC
        """), {"id": review_id}).mappings().all()
    return [dict(row) for row in rows]


@router.get("/internal/review-reminders/{job_id}")
def review_reminder_payload(job_id: str, x_review_internal_token: str | None = Header(default=None)):
    token = os.getenv("REVIEW_INTERNAL_TOKEN")
    if not token or not x_review_internal_token or not secrets.compare_digest(x_review_internal_token, token):
        raise HTTPException(403, "Acceso denegado.")
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT rr.id, rr.status, rr.user_id, b.id AS booking_id, b.check_in, b.check_out,
                   b.status AS booking_status,
                   b.guest_id, b.owner_id, b.quinta_title,
                   u.email, u.name, u.review_reminders_enabled,
                   other.name AS other_name
            FROM review_reminders rr JOIN bookings b ON b.id = rr.booking_id
            JOIN users u ON u.id = rr.user_id
            JOIN users other ON other.id = CASE WHEN rr.user_id = b.guest_id THEN b.owner_id ELSE b.guest_id END
            WHERE rr.id = :id
        """), {"id": job_id}).mappings().first()
        if row is None or row["status"] != "leased" or not row["review_reminders_enabled"] or not row["email"]:
            raise HTTPException(404, "Recordatorio no disponible.")
        exists = conn.execute(text("SELECT id FROM reviews WHERE booking_id = :booking_id AND author_id = :author_id"),
                              {"booking_id": row["booking_id"], "author_id": row["user_id"]}).first()
        if exists or review_eligibility(dict(row) | {"status": row["booking_status"]}, row["user_id"], False, utc_now()):
            raise HTTPException(409, "La reserva ya no admite una reseña.")
    return {"job_id": row["id"], "booking_id": row["booking_id"], "email": row["email"],
            "recipient_name": (row["name"] or "Usuario").split()[0],
            "person_to_review": (row["other_name"] or "Usuario").split()[0],
            "quinta_title": row["quinta_title"], "check_in": row["check_in"], "check_out": row["check_out"],
            "role": "guest" if row["user_id"] == row["guest_id"] else "owner"}
