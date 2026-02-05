import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Cookie, FastAPI, HTTPException, Request, Response, status
from google.cloud import firestore

from pulsefm_auth.session import issue_session_token, verify_session_token
from pulsefm_firestore.client import get_firestore_client
from pulsefm_pubsub.utils import publish_json
from pulsefm_redis.client import get_redis_client

from pulsefm_vote_api.config import settings
from pulsefm_vote_api.redis_keys import (
    dedupe_key,
    minute_bucket,
    rate_limit_ip_key,
    rate_limit_session_key,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote API", version="1.0.0")


class VoteError(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_vote_state(db: firestore.Client) -> Dict[str, Any]:
    doc_ref = db.collection(settings.firestore_vote_state_collection).document("current")
    doc = doc_ref.get()
    if not doc.exists:
        raise VoteError(status.HTTP_404_NOT_FOUND, "Vote window not initialized")
    return doc.to_dict() or {}


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid timestamp in vote state")


def _serialize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return None


def _enforce_rate_limit(redis_client, key: str, limit: int) -> None:
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)
    if count > limit:
        raise VoteError(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


@app.post("/session")
def create_session(response: Response) -> Dict[str, str]:
    token, meta = issue_session_token(settings.jwt_secret, settings.session_ttl_seconds)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.cookie_max_age(),
    )

    return {
        "sessionId": meta["session_id"],
        "expiresAt": meta["expires_at"].isoformat(),
    }


@app.get("/window")
def get_window() -> Dict[str, Any]:
    db = get_firestore_client()
    state = _get_vote_state(db)
    return {
        "windowId": state.get("windowId"),
        "status": state.get("status"),
        "startAt": _serialize_timestamp(state.get("startAt")),
        "endAt": _serialize_timestamp(state.get("endAt")),
        "options": state.get("options", []),
        "version": state.get("version"),
    }


@app.post("/vote")
def submit_vote(request: Request, payload: Dict[str, Any], session_cookie: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name)) -> Dict[str, Any]:
    if not session_cookie:
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Missing session cookie")

    try:
        claims = verify_session_token(session_cookie, settings.jwt_secret)
    except Exception:
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    session_id = claims.get("sid")
    if not session_id:
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    option = payload.get("option")
    if not option:
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing option")

    db = get_firestore_client()
    state = _get_vote_state(db)
    if state.get("status") != "OPEN":
        raise VoteError(status.HTTP_409_CONFLICT, "Voting window is closed")

    options = state.get("options") or []
    if option not in options:
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid option")

    end_at = _parse_timestamp(state.get("endAt"))
    now = datetime.now(timezone.utc)
    if now >= end_at:
        raise VoteError(status.HTTP_409_CONFLICT, "Voting window has ended")

    redis_client = get_redis_client()
    bucket = minute_bucket(now)
    _enforce_rate_limit(redis_client, rate_limit_session_key(session_id, bucket), settings.rate_limit_session_per_min)

    ip = _get_client_ip(request)
    _enforce_rate_limit(redis_client, rate_limit_ip_key(ip, bucket), settings.rate_limit_ip_per_min)

    ttl = int((end_at - now).total_seconds())
    ttl = max(ttl, 1)

    key = dedupe_key(state.get("windowId"), session_id)
    set_ok = redis_client.set(key, option, nx=True, ex=ttl)
    if not set_ok:
        raise VoteError(status.HTTP_409_CONFLICT, "Duplicate vote")

    event = {
        "windowId": state.get("windowId"),
        "option": option,
        "sessionId": session_id,
        "votedAt": now.isoformat(),
        "version": state.get("version"),
    }
    publish_json(settings.vote_events_topic, event)

    return {"status": "ok"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
