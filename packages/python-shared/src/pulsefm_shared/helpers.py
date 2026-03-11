from __future__ import annotations

"""Shared helper utilities for PulseFM Python services."""

from datetime import datetime, timezone
from typing import Any


def utc_ms() -> int:
    """Return the current UTC timestamp in milliseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def parse_int(value: Any, default: int | None = None) -> int | None:
    """Best-effort integer parsing with a fallback default value."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

