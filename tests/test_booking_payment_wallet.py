"""Payment-to-wallet regression tests; no application startup or real DB access."""

import asyncio
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import create_engine, event, text


@pytest.fixture
def payments_api(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def add_now(connection, _):
        connection.create_function("NOW", 0, lambda: datetime.utcnow().isoformat())

    # Import only the booking router with an isolated engine. Importing main.py
    # would load routers that perform DDL against the configured MySQL database.
    database = ModuleType("Database.getConnection")
    database.engine = engine
    monkeypatch.setitem(sys.modules, "Database.getConnection", database)
    spec = importlib.util.spec_from_file_location("bookings_under_test", root / "routers/bookings.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE bookings (
                id TEXT PRIMARY KEY, owner_id TEXT, guest_id TEXT, quinta_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE booking_payments (
                id TEXT PRIMARY KEY, booking_id TEXT, payment_type TEXT,
                amount NUMERIC, currency TEXT, status TEXT,
                rebill_payment_link_id TEXT, rebill_payment_link_url TEXT,
                rebill_transaction_id TEXT, payment_expire TEXT,
                created_at TEXT, updated_at TEXT, paid_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, owner_id TEXT, client_id TEXT,
                quinta_id TEXT, booking_id TEXT, amount NUMERIC,
                currency TEXT, status TEXT, description TEXT
            )
        """))
        conn.execute(text("INSERT INTO bookings VALUES ('booking-1', 'owner-1', 'guest-1', 'quinta-1')"))
        conn.execute(text("""
            INSERT INTO booking_payments
                (id, booking_id, payment_type, amount, currency, status)
            VALUES (:id, 'booking-1', :type, 500, 'ARS', :status)
        """), [
            {"id": "deposit-1", "type": "deposit", "status": "link_deposit_sent"},
            {"id": "balance-1", "type": "balance", "status": "link_balance_sent"},
        ])

    yield api, engine
    engine.dispose()


@pytest.mark.parametrize("status", ["finished", "FINISHED"])
def test_deposit_and_finished_balance_are_credited_once(payments_api, status):
    api, engine = payments_api
    asyncio.run(api.update_booking_payment("deposit-1", api.BookingPaymentUpdate(status="paid")))
    payload = api.BookingPaymentUpdate(
        status=status, rebill_transaction_id="rebill-balance-1",
        paid_at=datetime(2026, 10, 4, 12, 0),
    )
    asyncio.run(api.update_booking_payment("balance-1", payload))
    # A repeated confirmation must not produce a second wallet movement.
    asyncio.run(api.update_booking_payment("balance-1", payload))

    with engine.connect() as conn:
        movements = conn.execute(text("SELECT * FROM transactions")).mappings().all()
        balance = conn.execute(text("SELECT * FROM booking_payments WHERE id = 'balance-1'")).mappings().one()
    assert len(movements) == 2
    assert sum(row["amount"] for row in movements) == 1000
    assert {row["description"] for row in movements} == {
        "Pago reserva booking-1 (deposit)", "Pago reserva booking-1 (balance)",
    }
    for row in movements:
        assert row["status"] == "RETENIDO"
        assert row["currency"] == "ARS"
        assert row["owner_id"] == "owner-1"
        assert row["client_id"] == "guest-1"
    assert balance["status"] == status
    assert balance["rebill_transaction_id"] == "rebill-balance-1"
    assert datetime.fromisoformat(balance["paid_at"]) == payload.paid_at


@pytest.mark.parametrize("status", ["link_balance_sent", "rejected"])
def test_unpaid_balance_does_not_create_wallet_movement(payments_api, status):
    api, engine = payments_api
    asyncio.run(api.update_booking_payment("balance-1", api.BookingPaymentUpdate(status=status)))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar_one() == 0
        assert conn.execute(text("SELECT paid_at FROM booking_payments WHERE id = 'balance-1'")).scalar_one() is None


def test_create_finished_balance_sets_paid_at_and_credits_wallet(payments_api):
    api, engine = payments_api
    result = asyncio.run(api.create_booking_payment("booking-1", api.BookingPaymentCreate(
        payment_type="balance", amount=750, currency="USD", status="finished",
    )))
    with engine.connect() as conn:
        payment = conn.execute(text("SELECT * FROM booking_payments WHERE id = :id"), {"id": result["id"]}).mappings().one()
        movement = conn.execute(text("SELECT * FROM transactions")).mappings().one()
    assert payment["paid_at"] is not None
    assert movement["amount"] == 750
    assert movement["currency"] == "USD"
    assert movement["status"] == "RETENIDO"
