from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_epoch_ms(value: Any) -> int | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    return None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


def remaining_delay_seconds(ends_at: Any) -> int | None:
    if not ends_at:
        return None
    try:
        parsed = parse_timestamp(ends_at)
    except ValueError:
        return None
    delta = (parsed - utc_now()).total_seconds()
    return max(0, int(delta))
