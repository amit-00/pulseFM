import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

DEFAULT_COOKIE_NAME = "pulsefm_session"
DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def issue_session_token(secret: str | None = None, ttl_seconds: int | None = None) -> tuple[str, Dict[str, Any]]:
    secret = secret or os.getenv("SESSION_JWT_SECRET", "")
    if not secret:
        raise ValueError("SESSION_JWT_SECRET is required")

    ttl = ttl_seconds or int(os.getenv("SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS))
    session_id = str(uuid.uuid4())
    now = _utc_now()
    exp = now + timedelta(seconds=ttl)

    payload = {
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token, {"session_id": session_id, "expires_at": exp}


def verify_session_token(token: str, secret: str | None = None) -> Dict[str, Any]:
    secret = secret or os.getenv("SESSION_JWT_SECRET", "")
    if not secret:
        raise ValueError("SESSION_JWT_SECRET is required")

    return jwt.decode(token, secret, algorithms=["HS256"])
