import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from test_admin_owner_overview import overview


@pytest.fixture
def guest(overview):
    client, app, admin = overview
    with admin.engine.begin() as conn:
        for sql in [
            "ALTER TABLE bookings ADD COLUMN check_out TEXT",
            "ALTER TABLE booking_payments ADD COLUMN rebill_payment_link_url TEXT",
            "ALTER TABLE booking_payments ADD COLUMN payment_expire TEXT",
            "CREATE TABLE favorites (id TEXT, user_id TEXT, quinta_id TEXT, created_at TEXT)",
            "UPDATE bookings SET check_out='2020-01-01'",
            "UPDATE quintas SET status='active' WHERE id='owner'",
            "INSERT INTO favorites VALUES ('a','other','owner','2020-01-01'), ('b','owner','other','2020-01-01')",
        ]:
            conn.execute(text(sql))
    modules = {}
    for name in ["guest", "reviews", "favorites"]:
        spec = importlib.util.spec_from_file_location(name + "_under_test", Path(__file__).resolve().parents[1] / "routers" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app.include_router(module.router)
        modules[name] = module
    return client, app, admin, modules


def test_guest_requires_authentication(guest):
    client, _, _, _ = guest
    assert client.get("/guest/overview").status_code == 401
    assert client.post("/reviews", json={"booking_id": "3", "stars": 5}).status_code == 401


def test_guest_data_is_scoped_and_review_eligibility(guest):
    client, app, admin, _ = guest
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    data = client.get("/guest/overview").json()
    assert len(data["bookings"]) == 6
    assert all(b["guest_id"] == "other" for b in data["bookings"])
    assert [r["id"] for r in data["reviews"]] == ["own-review"]
    assert [f["id"] for f in data["favorites"]] == ["owner"]
    assert not any(b["can_review"] for b in data["bookings"])
    assert [p["id"] for b in data["bookings"] for p in b["payments"]] == ["0"]
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
    assert next(b for b in client.get("/guest/overview").json()["bookings"] if b["id"] == "3")["can_review"]
    app.dependency_overrides[admin.get_current_user] = lambda: "owner"
    assert client.get("/guest/overview").json()["favorites"] == []


def test_review_ownership_duplicates_and_owner_average(guest):
    client, app, admin, _ = guest
    payload = {"booking_id": "3", "stars": 4, "review_text": "Good"}
    app.dependency_overrides[admin.get_current_user] = lambda: "owner"
    assert client.post("/reviews", json=payload).status_code == 403
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.post("/reviews", json=payload).status_code == 409
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
    assert client.post("/reviews", json=payload).status_code == 200
    assert client.post("/reviews", json=payload).status_code == 409
    with admin.engine.connect() as conn:
        assert conn.execute(text("SELECT average_opinions FROM users WHERE id='owner'")).scalar() == 4


@pytest.mark.parametrize("status,checkout", [("paid","2020-01-01"),("pending","2020-01-01"),("finished","2099-01-01"),(None,"2020-01-01")])
def test_review_requires_completed_paid_stay(guest, status, checkout):
    client, app, admin, _ = guest
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews"))
        conn.execute(text("UPDATE bookings SET status=:status, check_out=:checkout WHERE id='3'"), {"status":status,"checkout":checkout})
    assert client.post("/reviews", json={"booking_id":"3","stars":5}).status_code == 409


def test_favorite_ownership_and_delete(guest):
    client, app, admin, _ = guest
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.delete("/favorites/owner/other").status_code == 403
    assert client.get("/favorites/owner").status_code == 403
    assert client.post("/favorites", json={"user_id":"owner","quinta_id":"owner"}).status_code == 403
    assert client.delete("/favorites/other/owner").status_code == 200
    assert client.get("/guest/overview").json()["favorites"] == []


@pytest.mark.parametrize("stars", [0,6])
def test_invalid_rating(guest, stars):
    client, app, admin, _ = guest
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.post("/reviews", json={"booking_id":"3","stars":stars}).status_code == 422
