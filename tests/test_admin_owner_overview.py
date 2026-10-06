"""Exercise the actual HTTP route against SQLite without importing main.py."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


@pytest.fixture
def overview(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database = ModuleType("Database.getConnection")
    database.engine = engine
    monkeypatch.setitem(sys.modules, "Database.getConnection", database)
    spec = importlib.util.spec_from_file_location("admin_under_test", root / "routers/admin.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    schema = [
        "CREATE TABLE users (id TEXT, role TEXT, name TEXT, email TEXT, phone TEXT, address TEXT, description TEXT, created_at TEXT, owner_location TEXT, average_opinions REAL, password_hash TEXT)",
        "CREATE TABLE users_picture (id TEXT, url TEXT, user_id TEXT)",
        "CREATE TABLE quintas (id TEXT, owner_id TEXT, title TEXT, address TEXT, city TEXT, status TEXT, price NUMERIC, currency_price TEXT, guests INT, bedrooms INT, bathrooms INT, rental_start_date TEXT, rental_end_date TEXT, created_at TEXT)",
        "CREATE TABLE quintas_main_images (quinta_id TEXT, url TEXT)",
        "CREATE TABLE bookings (id TEXT, quinta_id TEXT, owner_id TEXT, guest_id TEXT, status TEXT, created_at TEXT)",
        "CREATE TABLE booking_payments (id TEXT, booking_id TEXT, payment_type TEXT, amount NUMERIC, currency TEXT, status TEXT, created_at TEXT, paid_at TEXT)",
        "CREATE TABLE transactions (id TEXT, owner_id TEXT, quinta_id TEXT, booking_id TEXT, amount NUMERIC, currency TEXT, status TEXT, created_at TEXT, description TEXT, transfer_date_estimate TEXT)",
    ]
    with engine.begin() as conn:
        for statement in schema:
            conn.execute(text(statement))
        for uid, role in [("admin", "admin"), ("owner", "user"), ("other", "user")]:
            conn.execute(text("INSERT INTO users (id, role, name, password_hash) VALUES (:id, :role, :id, 'secret')"), {"id": uid, "role": role})
        for uid in ["owner", "other"]:
            conn.execute(text("INSERT INTO quintas (id, owner_id, title, status) VALUES (:id, :id, :id, 'pending')"), {"id": uid})
        for index, status in enumerate(["pending", "accepted", "paid", "finished", "rejected", "cancelled"]):
            conn.execute(text("INSERT INTO bookings VALUES (:id, 'owner', 'owner', 'other', :status, '2026-10-05')"), {"id": str(index), "status": status})
        conn.execute(text("INSERT INTO bookings VALUES ('foreign', 'other', 'other', 'owner', 'pending', '2026-10-05')"))
        for bid in ["0", "foreign"]:
            conn.execute(text("INSERT INTO booking_payments (id, booking_id, amount, status) VALUES (:id, :id, 12, 'paid')"), {"id": bid})
        for index, (owner, status, currency, amount) in enumerate([
            ("owner", "RETENIDO", "ARS", 100.25), ("owner", "DISPONIBLE", "USD", 50),
            ("owner", "ENTREGADO", "ARS", 20), ("owner", "CANCELLED", "ARS", 900),
            ("other", "DISPONIBLE", "ARS", 999),
        ]):
            conn.execute(text("INSERT INTO transactions (id, owner_id, quinta_id, status, currency, amount) VALUES (:id, :owner, :owner, :status, :currency, :amount)"),
                         {"id": str(index), "owner": owner, "status": status, "currency": currency, "amount": amount})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE reviews (id TEXT PRIMARY KEY, booking_id TEXT, stars INTEGER, review_text TEXT, created_at TEXT)"))
        conn.execute(text("INSERT INTO reviews VALUES ('own-review', '3', 5, 'Great', '2026-01-01'), ('foreign-review', 'foreign', 2, 'Other', '2026-01-01')"))
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield client, app, api
    engine.dispose()


def test_requires_authentication(overview):
    client, _, _ = overview
    assert client.get("/admin/owners/owner/overview").status_code == 401


@pytest.mark.parametrize("actor", ["owner", "other", "deleted"])
def test_non_admin_cannot_access_even_own_profile(overview, actor):
    client, app, api = overview
    app.dependency_overrides[api.get_current_user] = lambda: actor
    assert client.get("/admin/owners/owner/overview").status_code == 403


def test_admin_gets_all_statuses_and_only_target_owner(overview):
    client, app, api = overview
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    response = client.get("/admin/owners/owner/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["owner"]["id"] == "owner"
    assert "password_hash" not in data["owner"]
    assert "password" not in data["owner"]
    assert [q["id"] for q in data["properties"]] == ["owner"]
    assert {b["status"] for b in data["bookings"]} == {"pending", "accepted", "paid", "finished", "rejected", "cancelled"}
    assert [p["booking_id"] for p in data["payments"]] == ["0"]
    assert [r["id"] for r in data["reviews"]] == ["own-review"]
    assert data["reviews"][0]["stars"] == 5
    assert len(data["transactions"]) == 4
    assert data["balances"] == {
        "retenido": {"ARS": 100.25, "USD": 0},
        "disponible": {"ARS": 0, "USD": 50},
        "entregado": {"ARS": 20, "USD": 0},
    }


def test_missing_client_and_empty_client(overview):
    client, app, api = overview
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    assert client.get("/admin/owners/missing/overview").status_code == 404
    data = client.get("/admin/owners/admin/overview").json()
    assert data["properties"] == data["bookings"] == data["payments"] == data["transactions"] == []
    assert data["balances"]["retenido"] == {"ARS": 0, "USD": 0}
