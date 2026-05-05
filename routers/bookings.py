from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from Database.getConnection import engine
from models.bookings import (
    BookingCreate,
    BookingPaymentCreate,
    BookingPaymentUpdate,
    BookingStatusUpdate,
)

router = APIRouter()

PAID_STATUSES = {"PAID", "APPROVED", "APROBADO", "PAGADO", "COMPLETADO", "COMPLETED"}


def _row_to_dict(row):
    return dict(row._mapping) if row else None


def _payment_is_paid(status: str | None) -> bool:
    return bool(status and status.upper() in PAID_STATUSES)


def _create_wallet_transaction_for_payment(conn, payment_id: str):
    payment = conn.execute(
        text("""
            SELECT bp.*, b.owner_id, b.guest_id, b.quinta_id
            FROM booking_payments bp
            INNER JOIN bookings b ON bp.booking_id = b.id
            WHERE bp.id = :id
        """),
        {"id": payment_id},
    ).mappings().first()
    if not payment or not _payment_is_paid(payment["status"]):
        return

    description = f"Pago reserva {payment['booking_id']} ({payment['payment_type'] or 'booking'})"
    existing = conn.execute(
        text("""
            SELECT id FROM transactions
            WHERE booking_id = :booking_id
              AND owner_id = :owner_id
              AND client_id = :client_id
              AND amount = :amount
              AND currency = :currency
              AND description = :description
        """),
        {
            "booking_id": payment["booking_id"],
            "owner_id": payment["owner_id"],
            "client_id": payment["guest_id"],
            "amount": payment["amount"] or 0,
            "currency": payment["currency"] or "ARS",
            "description": description,
        },
    ).fetchone()
    if existing:
        return

    conn.execute(
        text("""
            INSERT INTO transactions (
                id, owner_id, client_id, quinta_id, booking_id, amount,
                currency, status, description
            ) VALUES (
                :id, :owner_id, :client_id, :quinta_id, :booking_id, :amount,
                :currency, 'RETENIDO', :description
            )
        """),
        {
            "id": str(uuid.uuid4()),
            "owner_id": payment["owner_id"],
            "client_id": payment["guest_id"],
            "quinta_id": payment["quinta_id"],
            "booking_id": payment["booking_id"],
            "amount": payment["amount"] or 0,
            "currency": payment["currency"] or "ARS",
            "description": description,
        },
    )


@router.post("/bookings", tags=["Bookings"])
async def create_booking(data: BookingCreate):
    try:
        booking_id = str(uuid.uuid4())
        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM quintas WHERE id = :id"), {"id": data.quinta_id}).fetchone():
                raise HTTPException(status_code=404, detail="Quinta no encontrada.")
            if not conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": data.guest_id}).fetchone():
                raise HTTPException(status_code=404, detail="Usuario invitado no encontrado.")
            if not conn.execute(text("SELECT id FROM users WHERE id = :id"), {"id": data.owner_id}).fetchone():
                raise HTTPException(status_code=404, detail="Usuario propietario no encontrado.")

            conn.execute(
                text("""
                    INSERT INTO bookings (
                        id, quinta_id, guest_id, owner_id, check_in, check_out,
                        quinta_title, payment_type, quinta_address, quinta_main_image,
                        guest_count, message, currency_price, amount, status,
                        created_at, updated_at
                    ) VALUES (
                        :id, :quinta_id, :guest_id, :owner_id, :check_in, :check_out,
                        :quinta_title, :payment_type, :quinta_address, :quinta_main_image,
                        :guest_count, :message, :currency_price, :amount, :status,
                        NOW(), NOW()
                    )
                """),
                {
                    "id": booking_id,
                    "quinta_id": data.quinta_id,
                    "guest_id": data.guest_id,
                    "owner_id": data.owner_id,
                    "check_in": data.check_in,
                    "check_out": data.check_out,
                    "guest_count": data.guest_count,
                    "message": data.message,
                    "currency_price": data.currency_price,
                    "amount": data.amount,
                    "status": data.status,
                    "payment_type": data.payment_type,
                    "quinta_title": data.quinta_title,
                    "quinta_address": data.quinta_address,
                    "quinta_main_image": data.quinta_main_image,
                },
            )
        return {"message": "Reserva creada exitosamente.", "id": booking_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/getBookingsInDate", tags=["Bookings"])
async def get_bookings():
    """
    Devuelve todas las reservas actualmente en curso.
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT b.*, q.title AS quinta_title
                    FROM bookings b
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    WHERE CURRENT_DATE >= b.check_in
                      AND CURRENT_DATE < b.check_out
                      AND b.status != 'rejected'
                      AND b.status != 'cancelled'
                    ORDER BY b.created_at DESC
                """)
            ).mappings().all()

        return [dict(row) for row in rows]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.get("/getBookingsFinished", tags=["Bookings"])
async def get_bookings_finished():
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT b.*, q.title AS quinta_title
                    FROM bookings b
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    WHERE b.status = 'FINISHED'
                    ORDER BY b.created_at DESC
                """),
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/guest/{guest_id}", tags=["Bookings"])
async def get_guest_bookings(guest_id: str):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT b.*, q.title AS quinta_title
                    FROM bookings b
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    WHERE b.guest_id = :guest_id
                    ORDER BY b.created_at DESC
                """),
                {"guest_id": guest_id},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/owner/{owner_id}", tags=["Bookings"])
async def get_owner_bookings(owner_id: str):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT b.*, q.title AS quinta_title, u.email AS guest_email
                    FROM bookings b
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    LEFT JOIN users u ON b.guest_id = u.id
                    WHERE b.owner_id = :owner_id
                    ORDER BY b.created_at DESC
                """),
                {"owner_id": owner_id},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/{booking_id}", tags=["Bookings"])
async def get_booking(booking_id: str):
    try:
        with engine.begin() as conn:
            booking = conn.execute(
                text("""
                    SELECT b.*, q.title AS quinta_title
                    FROM bookings b
                    LEFT JOIN quintas q ON b.quinta_id = q.id
                    WHERE b.id = :id
                """),
                {"id": booking_id},
            ).fetchone()
            if not booking:
                raise HTTPException(status_code=404, detail="Reserva no encontrada.")

            data = _row_to_dict(booking)
            payments = conn.execute(
                text("SELECT * FROM booking_payments WHERE booking_id = :id ORDER BY created_at DESC"),
                {"id": booking_id},
            ).mappings().all()
            data["payments"] = [dict(payment) for payment in payments]
            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/bookings/{booking_id}/status", tags=["Bookings"])
async def update_booking_status(booking_id: str, data: BookingStatusUpdate):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE bookings SET status = :status, updated_at = NOW() WHERE id = :id"),
                {"status": data.status, "id": booking_id},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Reserva no encontrada.")
        return {"message": "Estado de reserva actualizado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bookings/{booking_id}", tags=["Bookings"])
async def cancel_booking(booking_id: str):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE bookings SET status = 'CANCELADO', updated_at = NOW() WHERE id = :id"),
                {"id": booking_id},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Reserva no encontrada.")
        return {"message": "Reserva cancelada correctamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bookings/{booking_id}/payments", tags=["Booking Payments"])
async def create_booking_payment(booking_id: str, data: BookingPaymentCreate):
    try:
        payment_id = str(uuid.uuid4())
        paid_at = data.paid_at or (datetime.utcnow() if _payment_is_paid(data.status) else None)
        with engine.begin() as conn:
            if not conn.execute(text("SELECT id FROM bookings WHERE id = :id"), {"id": booking_id}).fetchone():
                raise HTTPException(status_code=404, detail="Reserva no encontrada.")

            conn.execute(
                text("""
                    INSERT INTO booking_payments (
                        id, booking_id, payment_type, amount, currency, status,
                        rebill_payment_link_id, rebill_payment_link_url,
                        rebill_transaction_id, payment_expire, created_at,
                        updated_at, paid_at
                    ) VALUES (
                        :id, :booking_id, :payment_type, :amount, :currency, :status,
                        :rebill_payment_link_id, :rebill_payment_link_url,
                        :rebill_transaction_id, :payment_expire, NOW(),
                        NOW(), :paid_at
                    )
                """),
                {
                    "id": payment_id,
                    "booking_id": booking_id,
                    "payment_type": data.payment_type,
                    "amount": data.amount,
                    "currency": data.currency,
                    "status": data.status,
                    "rebill_payment_link_id": data.rebill_payment_link_id,
                    "rebill_payment_link_url": data.rebill_payment_link_url,
                    "rebill_transaction_id": data.rebill_transaction_id,
                    "payment_expire": data.payment_expire,
                    "paid_at": paid_at,
                },
            )
            _create_wallet_transaction_for_payment(conn, payment_id)
        return {"message": "Pago de reserva creado exitosamente.", "id": payment_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bookings/{booking_id}/payments", tags=["Booking Payments"])
async def get_booking_payments(booking_id: str):
    try:
        with engine.begin() as conn:
            payments = conn.execute(
                text("SELECT * FROM booking_payments WHERE booking_id = :id ORDER BY created_at DESC"),
                {"id": booking_id},
            ).mappings().all()
            return [dict(payment) for payment in payments]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/booking-payments/{payment_id}", tags=["Booking Payments"])
async def update_booking_payment(payment_id: str, data: BookingPaymentUpdate):
    try:
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=422, detail="No hay campos para actualizar.")
        if _payment_is_paid(values.get("status")) and "paid_at" not in values:
            values["paid_at"] = datetime.utcnow()

        set_clause = ", ".join(f"{field} = :{field}" for field in values)
        values["id"] = payment_id
        with engine.begin() as conn:
            result = conn.execute(
                text(f"UPDATE booking_payments SET {set_clause}, updated_at = NOW() WHERE id = :id"),
                values,
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Pago de reserva no encontrado.")
            _create_wallet_transaction_for_payment(conn, payment_id)
        return {"message": "Pago de reserva actualizado correctamente."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
