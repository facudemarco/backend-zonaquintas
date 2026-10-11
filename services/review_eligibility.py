"""Shared review window for the two participants of a completed booking."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
FINISHED_STATUSES = {"FINISHED", "COMPLETED", "COMPLETADO", "FINALIZADO"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def review_window(booking) -> tuple[datetime, datetime] | None:
    try:
        checkout = date.fromisoformat(str(booking["check_out"])[:10])
    except (KeyError, TypeError, ValueError):
        return None
    opens = datetime.combine(checkout + timedelta(days=1), time.min, ARGENTINA)
    deadline = datetime.combine(checkout + timedelta(days=15), time.min, ARGENTINA)
    return opens.astimezone(timezone.utc).replace(tzinfo=None), deadline.astimezone(timezone.utc).replace(tzinfo=None)


def review_eligibility(booking, user_id: str | None = None, own_review: bool = False, now: datetime | None = None) -> str | None:
    if user_id is not None:
        if user_id not in (booking.get("guest_id"), booking.get("owner_id")):
            return "not_participant"
        if booking.get("guest_id") == booking.get("owner_id"):
            return "self_booking"
    if own_review:
        return "already_reviewed"
    if (booking.get("status") or "").upper() not in FINISHED_STATUSES:
        return "not_completed"
    window = review_window(booking)
    if window is None:
        return "not_open"
    current = now or utc_now()
    if current < window[0]:
        return "not_open"
    if current >= window[1]:
        return "expired"
    return None


def can_review(booking, user_id: str | None = None, own_review: bool = False, now: datetime | None = None) -> bool:
    return review_eligibility(booking, user_id, own_review, now) is None
