import importlib.util
from datetime import datetime, timedelta, timezone
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
            "ALTER TABLE bookings ADD COLUMN check_in TEXT",
            "ALTER TABLE bookings ADD COLUMN quinta_title TEXT",
            "ALTER TABLE booking_payments ADD COLUMN rebill_payment_link_url TEXT",
            "ALTER TABLE booking_payments ADD COLUMN payment_expire TEXT",
            "CREATE TABLE favorites (id TEXT, user_id TEXT, quinta_id TEXT, created_at TEXT)",
            "ALTER TABLE reviews ADD COLUMN author_id TEXT",
            "CREATE TABLE review_reminders (booking_id TEXT, user_id TEXT, status TEXT, lease_until TEXT)",
            "CREATE TABLE review_reports (id TEXT, review_id TEXT, reporter_id TEXT, reason TEXT, detail TEXT, status TEXT, created_at TEXT, resolved_at TEXT, UNIQUE(review_id, reporter_id))",
            "CREATE TABLE review_moderation_events (id TEXT, review_id TEXT, admin_id TEXT, action TEXT, old_status TEXT, new_status TEXT, reason TEXT, created_at TEXT)",
            "UPDATE bookings SET check_out='2020-01-01'",
            "UPDATE reviews SET author_id='other', recipient_id='owner', direction='guest_to_owner', reveal_at='2026-01-01', moderation_status='visible' WHERE id='own-review'",
            "UPDATE reviews SET author_id='owner', recipient_id='other', direction='guest_to_owner', reveal_at='2026-01-01', moderation_status='visible' WHERE id='foreign-review'",
            "UPDATE quintas SET status='active' WHERE id='owner'",
            "INSERT INTO favorites VALUES ('a','other','owner','2020-01-01'), ('b','owner','other','2020-01-01')",
        ]:
            conn.execute(text(sql))
        yesterday = datetime.now(timezone(timedelta(hours=-3))).date() - timedelta(days=1)
        conn.execute(text("UPDATE bookings SET check_out=:date WHERE id='3'"), {"date": yesterday.isoformat()})
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
    assert client.post("/reviews", json=payload).status_code == 201
    with admin.engine.connect() as conn:
        assert conn.execute(text("SELECT average_opinions FROM users WHERE id='owner'")).scalar() == 5
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.post("/reviews", json=payload).status_code == 409
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
        conn.execute(text("UPDATE users SET average_opinions=NULL WHERE id='owner'"))
    assert client.post("/reviews", json=payload).status_code == 201
    assert client.post("/reviews", json=payload).status_code == 409
    before = client.get("/reviews/booking/3").json()
    assert before["written"]["stars"] == 4
    assert before["received"] is None
    with admin.engine.connect() as conn:
        assert conn.execute(text("SELECT average_opinions FROM users WHERE id='owner'")).scalar() is None
    app.dependency_overrides[admin.get_current_user] = lambda: "owner"
    assert client.post("/reviews", json={"booking_id":"3", "stars":2}).status_code == 201
    revealed = client.get("/reviews/booking/3").json()
    assert revealed["received"]["stars"] == 4
    with admin.engine.connect() as conn:
        assert conn.execute(text("SELECT average_opinions FROM users WHERE id='owner'")).scalar() == 4


def test_public_review_privacy_and_moderation(guest):
    client, app, admin, _ = guest
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    response = client.post("/reviews", json={"booking_id":"3", "stars":5, "review_text":"Bien"})
    assert response.status_code == 201
    review_id = response.json()["id"]
    assert client.get("/quintas/owner/reviews").json()["summary"]["count"] == 0
    app.dependency_overrides[admin.get_current_user] = lambda: "owner"
    assert client.post("/reviews", json={"booking_id":"3", "stars":3}).status_code == 201
    listing = client.get("/quintas/owner/reviews").json()
    assert listing["summary"]["count"] == 1
    assert listing["items"][0]["author_name"] == "other"
    assert "booking_id" not in listing["items"][0]
    assert "author_id" not in listing["items"][0]
    assert client.post(f"/reviews/{review_id}/reports", json={"reason":"inexacta"}).status_code == 201
    assert client.post(f"/reviews/{review_id}/reports", json={"reason":"inexacta"}).status_code == 409
    app.dependency_overrides[admin.get_current_user] = lambda: "admin"
    assert client.patch(f"/admin/reviews/{review_id}/moderation", json={"action":"hide","reason":"Dato privado"}).status_code == 200
    assert client.get("/quintas/owner/reviews").json()["summary"]["count"] == 0
    assert client.patch(f"/admin/reviews/{review_id}/moderation", json={"action":"restore","reason":"Corregido"}).status_code == 200
    assert client.get("/quintas/owner/reviews").json()["summary"]["count"] == 1


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


def test_review_window_closes_after_fourteen_full_calendar_days(guest):
    client, app, admin, _ = guest
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
        checkout = datetime.now(timezone(timedelta(hours=-3))).date() - timedelta(days=20)
        conn.execute(text("UPDATE bookings SET check_out=:checkout WHERE id='3'"), {"checkout": checkout.isoformat()})
    state = client.get("/reviews/booking/3").json()
    assert state["can_review"] is False
    assert state["review_reason"] == "expired"
    assert client.post("/reviews", json={"booking_id":"3","stars":5}).status_code == 409


def test_review_rejects_non_participant_and_invalid_payload(guest):
    client, app, admin, _ = guest
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
    app.dependency_overrides[admin.get_current_user] = lambda: "admin"
    assert client.get("/reviews/booking/3").status_code == 403
    assert client.post("/reviews", json={"booking_id":"3","stars":5}).status_code == 403
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.post("/reviews", json={"booking_id":"3","stars":True}).status_code == 422
    assert client.post("/reviews", json={"booking_id":"3","stars":5,"review_text":"x" * 2001}).status_code == 422
    assert client.get("/admin/reviews").status_code == 403


def test_guest_reputation_is_private_to_related_owner(guest):
    client, app, admin, _ = guest
    with admin.engine.begin() as conn:
        conn.execute(text("DELETE FROM reviews WHERE booking_id='3'"))
    app.dependency_overrides[admin.get_current_user] = lambda: "other"
    assert client.post("/reviews", json={"booking_id":"3","stars":5}).status_code == 201
    app.dependency_overrides[admin.get_current_user] = lambda: "owner"
    assert client.post("/reviews", json={"booking_id":"3","stars":2}).status_code == 201
    summary = client.get("/reviews/guest/other/summary").json()
    assert summary["count"] == 1 and summary["average"] == 2
    app.dependency_overrides[admin.get_current_user] = lambda: "admin"
    assert client.get("/reviews/guest/other/summary").status_code == 200
    app.dependency_overrides[admin.get_current_user] = lambda: "unrelated"
    assert client.get("/reviews/guest/other/summary").status_code == 403
