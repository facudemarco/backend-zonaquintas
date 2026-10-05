from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import text

RELEASED_STATUSES = ("rejected", "cancelled", "rechazado", "cancelado")
MIN_NIGHTS = 2


def validate_rental_period(start: date | None, end: date | None, *, required: bool = False):
    if not start and not end and not required:
        return
    if not start or not end or end <= start:
        raise HTTPException(422, "Seleccioná un rango de alquiler válido.")


def validate_stay(start: date, end: date, rental_start: date | None, rental_end: date | None, *, check_future: bool = True):
    if isinstance(rental_start, str):
        rental_start = date.fromisoformat(rental_start)
    if isinstance(rental_end, str):
        rental_end = date.fromisoformat(rental_end)
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    today = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    if (check_future and start < today) or (check_future and (end - start).days < MIN_NIGHTS) or end <= start:
        raise HTTPException(422, "La reserva debe ser futura y de al menos dos noches.")
    # NULL/NULL is a transitional legacy property, without a configured season.
    if rental_start and rental_end and (start < rental_start or end > rental_end):
        raise HTTPException(422, "Las fechas están fuera del período de alquiler.")


def lock_quinta(conn, quinta_id: str):
    suffix = " FOR UPDATE" if conn.dialect.name == "mysql" else ""
    return conn.execute(
        text("SELECT id, owner_id, status, rental_start_date, rental_end_date FROM quintas WHERE id = :id" + suffix),
        {"id": quinta_id},
    ).mappings().first()


def blocking_bookings(conn, quinta_id: str, start: date, end: date, exclude_id: str | None = None):
    return conn.execute(text("""
        SELECT id, check_in, check_out, status FROM bookings
        WHERE quinta_id = :quinta_id AND check_in < :end AND check_out > :start
          AND (status IS NULL OR LOWER(status) NOT IN
               ('rejected', 'cancelled', 'rechazado', 'cancelado'))
          AND (:exclude_id IS NULL OR id <> :exclude_id)
        ORDER BY check_in
    """), {"quinta_id": quinta_id, "start": start, "end": end, "exclude_id": exclude_id}).mappings().all()


def ensure_available(conn, quinta, start: date, end: date, exclude_id: str | None = None):
    if not quinta:
        raise HTTPException(404, "Quinta no encontrada.")
    if str(quinta["status"]).lower() != "active":
        raise HTTPException(409, "La quinta no está disponible para reservas.")
    validate_stay(start, end, quinta["rental_start_date"], quinta["rental_end_date"], check_future=exclude_id is None)
    if blocking_bookings(conn, quinta["id"], start, end, exclude_id):
        raise HTTPException(409, "Las fechas ya están reservadas.")
