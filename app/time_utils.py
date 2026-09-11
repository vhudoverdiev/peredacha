from __future__ import annotations

from datetime import datetime, timedelta, timezone


MOSCOW_TIMEZONE = timezone(timedelta(hours=3), name="MSK")


def to_moscow_datetime(value: datetime) -> datetime:
    """Treat naive database timestamps as UTC and return Moscow time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW_TIMEZONE)


def utc_now() -> datetime:
    """Return naive UTC datetime for legacy SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
