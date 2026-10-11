from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from services.review_reminders import _candidates, _scheduled


def test_reminder_schedule_uses_argentina_local_time():
    assert _scheduled(date(2026, 10, 5), 1) == datetime(2026, 10, 6, 13)
    assert _scheduled(date(2026, 10, 5), 2) == datetime(2026, 10, 13, 13)


def test_candidates_honor_opt_out_review_and_second_stage():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id TEXT, review_reminders_enabled INTEGER)"))
        conn.execute(text("CREATE TABLE bookings (id TEXT, guest_id TEXT, owner_id TEXT, check_out TEXT, status TEXT)"))
        conn.execute(text("CREATE TABLE reviews (id TEXT, booking_id TEXT, author_id TEXT)"))
        conn.execute(text("CREATE TABLE review_reminders (booking_id TEXT, user_id TEXT, stage INTEGER, status TEXT, sent_at TEXT)"))
        conn.execute(text("INSERT INTO users VALUES ('guest', 1), ('owner', 0)"))
        conn.execute(text("INSERT INTO bookings VALUES ('booking', 'guest', 'owner', '2026-10-05', 'finished')"))
        now = datetime(2026, 10, 6, 14)
        assert list(_candidates(conn, date(2026, 10, 1), now)) == [("booking", "guest", 1, datetime(2026, 10, 6, 13))]
        conn.execute(text("INSERT INTO review_reminders VALUES ('booking', 'guest', 1, 'sent', '2026-10-06 13:00:00')"))
        assert list(_candidates(conn, date(2026, 10, 1), datetime(2026, 10, 13, 13))) == [
            ("booking", "guest", 1, datetime(2026, 10, 6, 13)),
            ("booking", "guest", 2, datetime(2026, 10, 13, 13)),
        ]
        conn.execute(text("INSERT INTO reviews VALUES ('review', 'booking', 'guest')"))
        assert list(_candidates(conn, date(2026, 10, 1), datetime(2026, 10, 13, 13))) == []
