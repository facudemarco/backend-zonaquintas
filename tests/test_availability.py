from datetime import date, timedelta
import asyncio
import importlib
import sys
import types

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, event
from sqlalchemy.pool import StaticPool

from services.availability import blocking_bookings, ensure_available, lock_quinta


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def add_now(dbapi_connection, _):
        dbapi_connection.create_function("NOW", 0, lambda: "2026-10-04 12:00:00")
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE quintas (
            id TEXT PRIMARY KEY, owner_id TEXT, status TEXT,
            rental_start_date DATE, rental_end_date DATE)"""))
        conn.execute(text("""CREATE TABLE bookings (
            id TEXT PRIMARY KEY, quinta_id TEXT, guest_id TEXT, owner_id TEXT,
            check_in DATE, check_out DATE, status TEXT, payment_type TEXT,
            quinta_title TEXT, quinta_address TEXT, quinta_main_image TEXT,
            guest_count REAL, message TEXT, currency_price TEXT, amount REAL,
            created_at TEXT, updated_at TEXT)"""))
        conn.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users VALUES ('guest'), ('owner')"))
        conn.execute(text("""INSERT INTO quintas VALUES (
            'property', 'owner', 'active', '2099-01-01', '2099-12-31')"""))
    return engine


def booking(start, end, status="pending", booking_id="first"):
    from models.bookings import BookingCreate
    return BookingCreate(
        quinta_id="property", guest_id="guest", owner_id="owner",
        check_in=start, check_out=end, status=status,
        quinta_title="Quinta", quinta_address="Calle", quinta_main_image="image",
    )


def booking_router(database, monkeypatch):
    connection_module = types.ModuleType("Database.getConnection")
    connection_module.engine = database
    monkeypatch.setitem(sys.modules, "Database.getConnection", connection_module)
    route = importlib.import_module("routers.bookings")
    monkeypatch.setattr(route, "engine", database)
    return route


def quinta_router(database, monkeypatch):
    connection_module = types.ModuleType("Database.getConnection")
    connection_module.engine = database
    monkeypatch.setitem(sys.modules, "Database.getConnection", connection_module)
    route = importlib.import_module("routers.quintas")
    monkeypatch.setattr(route, "engine", database)
    return route


def test_create_blocks_overlap_and_releases_rejected(database, monkeypatch):
    route = booking_router(database, monkeypatch)
    start, end = date(2099, 3, 10), date(2099, 3, 12)
    first = asyncio.run(route.create_booking(booking(start, end), user_id="guest"))
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(route.create_booking(booking(start + timedelta(days=1), end + timedelta(days=1)), user_id="guest"))
    assert conflict.value.status_code == 409
    asyncio.run(route.update_booking_status(first["id"], route.BookingStatusUpdate(status="rejected")))
    asyncio.run(route.create_booking(booking(start, end), user_id="guest"))
    with pytest.raises(HTTPException) as reactivation:
        asyncio.run(route.update_booking_status(first["id"], route.BookingStatusUpdate(status="accepted")))
    assert reactivation.value.status_code == 409


def test_adjacent_stay_and_season_edges(database, monkeypatch):
    route = booking_router(database, monkeypatch)
    asyncio.run(route.create_booking(booking(date(2099, 1, 1), date(2099, 1, 3)), user_id="guest"))
    asyncio.run(route.create_booking(booking(date(2099, 1, 3), date(2099, 1, 5)), user_id="guest"))
    with pytest.raises(HTTPException) as outside:
        asyncio.run(route.create_booking(booking(date(2099, 12, 30), date(2100, 1, 1)), user_id="guest"))
    assert outside.value.status_code == 422


def test_late_payment_cannot_reactivate_released_booking(database, monkeypatch):
    route = booking_router(database, monkeypatch)
    created = asyncio.run(route.create_booking(booking(date(2099, 6, 1), date(2099, 6, 3)), user_id="guest"))
    asyncio.run(route.update_booking_status(created["id"], route.BookingStatusUpdate(status="cancelled")))
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(route.update_booking_status(created["id"], route.BookingStatusUpdate(status="paid")))
    assert conflict.value.status_code == 409


def test_unknown_status_remains_blocking(database):
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO bookings (id, quinta_id, check_in, check_out, status)
            VALUES ('legacy', 'property', '2099-02-01', '2099-02-04', 'mystery')"""))
        quinta = lock_quinta(conn, "property")
        with pytest.raises(HTTPException) as conflict:
            ensure_available(conn, quinta, date(2099, 2, 2), date(2099, 2, 5))
        assert conflict.value.status_code == 409


def test_public_availability_exposes_only_intervals(database, monkeypatch):
    route = quinta_router(database, monkeypatch)
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO bookings (id, quinta_id, guest_id, check_in, check_out, status)
            VALUES ('one', 'property', 'guest', '2099-03-10', '2099-03-12', 'pending'),
                   ('two', 'property', 'guest', '2099-03-15', '2099-03-17', 'cancelled')"""))
    response = asyncio.run(route.get_quinta_availability("property", date(2099, 3, 1), date(2099, 4, 1)))
    assert response["blocked"] == [{"check_in": "2099-03-10", "check_out": "2099-03-12"}]
    assert "guest" not in str(response)


def test_owner_cannot_shrink_period_over_booking(database, monkeypatch):
    route = quinta_router(database, monkeypatch)
    with database.begin() as conn:
        conn.execute(text("""INSERT INTO bookings (id, quinta_id, check_in, check_out, status)
            VALUES ('one', 'property', '2099-03-10', '2099-03-12', 'finished')"""))
    period = route.RentalPeriodUpdate(rental_start_date=date(2099, 4, 1), rental_end_date=date(2099, 5, 1))
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(route.update_rental_period("property", period, user_id="owner"))
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as forbidden:
        asyncio.run(route.update_rental_period("property", period, user_id="other"))
    assert forbidden.value.status_code == 403


def test_http_availability_and_owner_auth(database, monkeypatch):
    route = quinta_router(database, monkeypatch)
    app = FastAPI()
    app.include_router(route.router)
    client = TestClient(app)
    response = client.get("/quintas/property/availability?from=2099-03-01&to=2099-04-01")
    assert response.status_code == 200
    assert response.json()["quinta_id"] == "property"
    response = client.patch("/quintas/property/rental-period", json={
        "rental_start_date": "2099-03-01", "rental_end_date": "2099-04-01",
    })
    assert response.status_code == 401
