"""Regression coverage for deployments without the optional CRM schema."""
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
def dashboard(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    database = ModuleType("Database.getConnection")
    database.engine = engine
    monkeypatch.setitem(sys.modules, "Database.getConnection", database)
    spec = importlib.util.spec_from_file_location("dashboard_under_test", root / "routers/admin.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    with engine.begin() as conn:
        for statement in [
            "CREATE TABLE users (id TEXT, role TEXT, email TEXT)",
            "CREATE TABLE quintas (id TEXT, title TEXT, status TEXT)",
            "CREATE TABLE bookings (id TEXT, quinta_id TEXT, guest_id TEXT, owner_id TEXT, check_in TEXT, check_out TEXT, amount NUMERIC, currency_price TEXT, status TEXT, created_at TEXT, quinta_title TEXT)",
            "CREATE TABLE transactions (status TEXT, amount NUMERIC)",
            "INSERT INTO users VALUES ('admin', 'admin', 'admin@example.test'), ('owner', 'owner', 'owner@example.test'), ('guest', 'user', 'guest@example.test')",
            "INSERT INTO quintas VALUES ('q1', 'Quinta 1', 'ACTIVA'), ('q2', 'Quinta 2', 'ACTIVA'), ('q3', 'Quinta 3', 'ACTIVA'), ('q4', 'Quinta 4', 'ACTIVA')",
            "INSERT INTO bookings VALUES ('b1', 'q1', 'guest', 'owner', '2026-10-07', '2026-10-08', 150, 'ARS', 'paid', '2026-10-07', 'Old title')",
            "INSERT INTO transactions VALUES ('DISPONIBLE', 100)",
        ]:
            conn.execute(text(statement))
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app, api, engine
    engine.dispose()


def test_dashboard_without_crm_schema(dashboard):
    client, app, api, _ = dashboard
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_verifications"] == 4
    assert data["users"] == {"total": 3, "owners": 1, "guests": 2}
    assert data["bookings"]["gross_booking_volume"] == 150
    assert data["recent_bookings"][0]["quinta_title"] == "Quinta 1"
    assert data["transactions"]["by_status"]["DISPONIBLE"] == {"count": 1, "amount": 100}


def test_dashboard_with_crm_schema(dashboard):
    client, app, api, engine = dashboard
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE quinta_verifications (quinta_id TEXT PRIMARY KEY, status TEXT)"))
        conn.execute(text("INSERT INTO quinta_verifications VALUES ('q1', 'VERIFICADA'), ('q2', 'EN_REVISION'), ('q3', 'RECHAZADA')"))
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert response.json()["pending_verifications"] == 2


def test_empty_marketplace_without_crm_schema(dashboard):
    client, app, api, engine = dashboard
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    with engine.begin() as conn:
        for table in ("bookings", "transactions", "quintas"):
            conn.execute(text(f"DELETE FROM {table}"))
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert response.json()["pending_verifications"] == 0
    assert response.json()["recent_bookings"] == []


def test_dashboard_still_requires_admin(dashboard):
    client, app, api, _ = dashboard
    assert client.get("/admin/dashboard").status_code == 401
    app.dependency_overrides[api.get_current_user] = lambda: "guest"
    assert client.get("/admin/dashboard").status_code == 403


def test_unrelated_database_errors_are_not_hidden(dashboard):
    client, app, api, engine = dashboard
    app.dependency_overrides[api.get_current_user] = lambda: "admin"
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE transactions"))
    assert client.get("/admin/dashboard").status_code == 500
