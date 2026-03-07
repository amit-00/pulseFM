from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def parse_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_value(container: Any, key: str, default: Any = None) -> Any:
    if container is None:
        return default

    try:
        return container.get(key, default)
    except Exception:
        pass

    try:
        return getattr(container, key)
    except Exception:
        pass

    try:
        return container[key]
    except Exception:
        return default
