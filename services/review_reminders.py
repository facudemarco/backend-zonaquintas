"""Cron entrypoint: python -m services.review_reminders [--send].

Default is a read-only dry run. Sending requires --send and explicit server env.
"""

import argparse
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.review_eligibility import review_eligibility, review_window, utc_now

ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def _scheduled(check_out: date, stage: int) -> datetime:
    local = datetime.combine(check_out + timedelta(days=1 if stage == 1 else 8), time(10), ARGENTINA)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _candidates(conn, launch_date: date, now: datetime):
    today = now.replace(tzinfo=timezone.utc).astimezone(ARGENTINA).date()
    rows = conn.execute(text("""
        SELECT b.id, b.guest_id, b.owner_id, b.check_out, b.status,
               guest.review_reminders_enabled AS guest_enabled,
               owner.review_reminders_enabled AS owner_enabled
        FROM bookings b JOIN users guest ON guest.id = b.guest_id
        JOIN users owner ON owner.id = b.owner_id
        WHERE b.check_out >= :launch AND b.check_out < :today
          AND UPPER(b.status) IN ('FINISHED', 'COMPLETED', 'COMPLETADO', 'FINALIZADO')
    """), {"launch": launch_date, "today": today}).mappings().all()
    for booking in rows:
        booking = dict(booking)
        checkout = booking["check_out"]
        if isinstance(checkout, str):
            checkout = date.fromisoformat(checkout[:10])
        if review_window(booking)[1] <= now or booking["guest_id"] == booking["owner_id"]:
            continue
        for user_id, enabled in ((booking["guest_id"], booking["guest_enabled"]),
                                 (booking["owner_id"], booking["owner_enabled"])):
            if not enabled or review_eligibility(booking, user_id, False, now):
                continue
            reviewed = conn.execute(text("SELECT id FROM reviews WHERE booking_id = :id AND author_id = :user"),
                                    {"id": booking["id"], "user": user_id}).first()
            if reviewed:
                continue
            first = conn.execute(text("""
                SELECT status, sent_at FROM review_reminders
                WHERE booking_id = :id AND user_id = :user AND stage = 1
            """), {"id": booking["id"], "user": user_id}).mappings().first()
            for stage in (1, 2):
                due = _scheduled(checkout, stage)
                if due > now or due >= review_window(booking)[1]:
                    continue
                if stage == 2 and (not first or first["status"] != "sent" or not first["sent_at"]):
                    continue
                if stage == 2:
                    sent = first["sent_at"]
                    if isinstance(sent, str):
                        sent = datetime.fromisoformat(sent)
                    if sent + timedelta(days=7) > now:
                        continue
                yield booking["id"], user_id, stage, due


def _enqueue(engine, launch_date: date, now: datetime, dry_run: bool):
    with engine.connect() as conn:
        candidates = list(_candidates(conn, launch_date, now))
    if dry_run:
        print(f"review reminders dry-run: {len(candidates)} eligible stages")
        return
    for booking_id, user_id, stage, due in candidates:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO review_reminders (id, booking_id, user_id, stage, scheduled_at, status)
                    VALUES (:id, :booking_id, :user_id, :stage, :scheduled_at, 'pending')
                """), {"id": str(uuid.uuid4()), "booking_id": booking_id,
                       "user_id": user_id, "stage": stage, "scheduled_at": due})
        except IntegrityError:
            pass  # Unique (booking_id, user_id, stage) makes concurrent cron safe.


def _claim(engine, now: datetime):
    with engine.connect() as conn:
        jobs = conn.execute(text("""
            SELECT id FROM review_reminders
            WHERE scheduled_at <= :now AND attempts < 5
              AND (status = 'pending' OR (status = 'leased' AND lease_until < :now))
            ORDER BY scheduled_at LIMIT 50
        """), {"now": now}).scalars().all()
    for job_id in jobs:
        with engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE review_reminders
                SET status = 'leased', attempts = attempts + 1, lease_until = :lease
                WHERE id = :id AND scheduled_at <= :now AND attempts < 5
                  AND (status = 'pending' OR (status = 'leased' AND lease_until < :now))
            """), {"id": job_id, "now": now, "lease": now + timedelta(minutes=5)})
            if result.rowcount == 1:
                yield job_id


def _still_eligible(conn, job_id: str, now: datetime):
    row = conn.execute(text("""
        SELECT rr.booking_id, rr.user_id, rr.status, b.guest_id, b.owner_id, b.check_out,
               b.status AS booking_status, u.review_reminders_enabled
        FROM review_reminders rr JOIN bookings b ON b.id = rr.booking_id
        JOIN users u ON u.id = rr.user_id WHERE rr.id = :id
    """), {"id": job_id}).mappings().first()
    if not row or row["status"] != "leased" or not row["review_reminders_enabled"]:
        return False
    booking = dict(row) | {"status": row["booking_status"]}
    reviewed = conn.execute(text("SELECT id FROM reviews WHERE booking_id = :id AND author_id = :user"),
                            {"id": row["booking_id"], "user": row["user_id"]}).first()
    return reviewed is None and review_eligibility(booking, row["user_id"], False, now) is None


def _deliver(engine, mailer_url: str, token: str, now: datetime):
    for job_id in _claim(engine, now):
        with engine.begin() as conn:
            if not _still_eligible(conn, job_id, utc_now()):
                conn.execute(text("UPDATE review_reminders SET status='cancelled', lease_until=NULL WHERE id=:id"),
                             {"id": job_id})
                continue
        try:
            payload = json.dumps({"job_id": job_id}).encode("utf-8")
            request = Request(mailer_url, data=payload,
                              headers={"Content-Type": "application/json", "X-Review-Internal-Token": token},
                              method="POST")
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read())
            if not result.get("ok") or not result.get("id"):
                raise ValueError("Mailer did not confirm provider acceptance")
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE review_reminders SET status='sent', sent_at=:now,
                        provider_message_id=:provider_id, lease_until=NULL, last_error=NULL
                    WHERE id=:id AND status='leased'
                """), {"id": job_id, "now": utc_now(), "provider_id": result["id"]})
        except Exception as exc:
            # Never log email, credentials, provider response body or comments.
            with engine.begin() as conn:
                attempts = conn.execute(text("SELECT attempts FROM review_reminders WHERE id=:id"),
                                        {"id": job_id}).scalar() or 5
                status = "failed" if attempts >= 5 else "pending"
                conn.execute(text("""
                    UPDATE review_reminders SET status=:status, lease_until=NULL,
                        scheduled_at=:retry_at, last_error=:error WHERE id=:id
                """), {"id": job_id, "status": status,
                       "retry_at": utc_now() + timedelta(hours=min(2 ** attempts, 24)),
                       "error": type(exc).__name__})


def _reconcile_host_averages(engine, now: datetime):
    """Publish host averages after the blind-review deadline, even without a second review."""
    with engine.begin() as conn:
        owners = conn.execute(text("""
            SELECT DISTINCT recipient_id FROM reviews
            WHERE direction='guest_to_owner' AND reveal_at <= :now
        """), {"now": now}).scalars().all()
        for owner_id in owners:
            average = conn.execute(text("""
                SELECT AVG(stars) FROM reviews
                WHERE recipient_id=:id AND direction='guest_to_owner'
                  AND moderation_status='visible' AND reveal_at <= :now
            """), {"id": owner_id, "now": now}).scalar()
            conn.execute(text("UPDATE users SET average_opinions=:average WHERE id=:id"),
                         {"average": average, "id": owner_id})


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Create jobs and deliver them")
    args = parser.parse_args()
    launch_raw = os.getenv("REVIEW_LAUNCH_DATE")
    if not launch_raw:
        raise SystemExit("REVIEW_LAUNCH_DATE is required")
    launch_date = date.fromisoformat(launch_raw)
    if args.send:
        if os.getenv("REVIEW_REMINDERS_ENABLED") != "1":
            raise SystemExit("REVIEW_REMINDERS_ENABLED=1 is required for sending")
        mailer_url = os.getenv("REVIEW_MAILER_URL")
        token = os.getenv("REVIEW_INTERNAL_TOKEN")
        if not mailer_url or not token:
            raise SystemExit("REVIEW_MAILER_URL and REVIEW_INTERNAL_TOKEN are required")
    from Database.getConnection import engine
    now = utc_now()
    _enqueue(engine, launch_date, now, dry_run=not args.send)
    if args.send:
        _reconcile_host_averages(engine, now)
        _deliver(engine, mailer_url, token, now)


if __name__ == "__main__":
    main()
