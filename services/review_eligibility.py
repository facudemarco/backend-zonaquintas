from datetime import date, datetime, timedelta, timezone


def can_review(booking):
    if (booking.get("status") or "").upper() not in {"FINISHED", "COMPLETED", "COMPLETADO", "FINALIZADO"}:
        return False
    try:
        checkout = date.fromisoformat(str(booking["check_out"])[:10])
    except (ValueError, TypeError, KeyError):
        return False
    return checkout < datetime.now(timezone(timedelta(hours=-3))).date()
