import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Cookie, FastAPI, HTTPException, Response, status
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP
from google.cloud.storage import Client as StorageClient

from pulsefm_auth.session import issue_session_token, verify_session_token
from pulsefm_tasks.client import enqueue_json_task
from pulsefm_redis.client import fixed_window_allow, get_redis_client, has_voted_session, poll_tally_key, token_bucket_allow

from pulsefm_vote_api.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote API", version="1.0.0")
_db: AsyncClient | None = None
_storage: StorageClient | None = None


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db


def get_storage_client() -> StorageClient:
    global _storage
    if _storage is None:
        _storage = StorageClient()
    return _storage


class VoteError(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


def _rate_limited() -> None:
    raise VoteError(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")


async def _check_vote_rate_limits(redis_client, session_id: str, vote_id: str) -> None:
    sess_key = f"pulsefm:rl:vote:sess:{session_id}"
    poll_key = f"pulsefm:rl:vote:poll:{vote_id}"
    try:
        if not await fixed_window_allow(redis_client, sess_key, settings.vote_rl_sess_limit, settings.vote_rl_sess_window):
            _rate_limited()
        if not await fixed_window_allow(redis_client, poll_key, settings.vote_rl_poll_limit, settings.vote_rl_poll_window):
            _rate_limited()
    except Exception:
        logger.exception("Redis rate limit failed", extra={"sessionId": session_id, "voteId": vote_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")


async def _check_heartbeat_rate_limit(redis_client, session_id: str) -> None:
    key = f"pulsefm:rl:heartbeat:sess:{session_id}"
    try:
        if not await fixed_window_allow(redis_client, key, settings.vote_rl_sess_limit, settings.vote_rl_sess_window):
            _rate_limited()
    except Exception:
        logger.exception("Redis rate limit failed", extra={"sessionId": session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")


async def _check_download_rate_limit(redis_client, session_id: str, vote_id: str) -> None:
    key = f"pulsefm:rl:downloads:sess:{session_id}:poll:{vote_id}"
    try:
        if not await fixed_window_allow(redis_client, key, settings.vote_rl_sess_limit, settings.vote_rl_sess_window):
            _rate_limited()
    except Exception:
        logger.exception("Redis rate limit failed", extra={"sessionId": session_id, "voteId": vote_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")


async def _check_session_rate_limit(redis_client) -> None:
    capacity = settings.session_rl_burst
    refill_per_ms = (settings.session_rl_rate_per_min / 60) / 1000
    try:
        allowed = await token_bucket_allow(
            redis_client,
            "pulsefm:rl:session:bucket",
            "pulsefm:rl:session:rps",
            capacity,
            refill_per_ms,
            1,
            settings.session_rl_rps,
        )
        if not allowed:
            _rate_limited()
    except Exception:
        logger.exception("Redis rate limit failed for session bucket")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")


@app.post("/session")
async def create_session(response: Response) -> Dict[str, str]:
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for session")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")
    await _check_session_rate_limit(redis_client)
    token, meta = issue_session_token(settings.jwt_secret, settings.session_ttl_seconds)
    logger.info("Issued session", extra={"sessionId": meta["session_id"]})

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


@app.post("/heartbeat")
async def send_heartbeat(session_cookie: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name)):
    if not session_cookie:
        logger.warning("Missing session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Missing session cookie")

    try:
        claims = verify_session_token(session_cookie, settings.jwt_secret)
    except Exception:
        logger.warning("Invalid session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    session_id = claims.get("sid")
    if not session_id:
        logger.warning("Session cookie missing sid claim")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for heartbeat")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")
    await _check_heartbeat_rate_limit(redis_client, session_id)

    db = get_firestore_client()
    heartbeat_ref = db.collection(settings.firestore_heartbeats_collection).document(session_id)
    await heartbeat_ref.set({
        "sessionId": session_id,
        "heartbeatAt": SERVER_TIMESTAMP,
    })

    return {"status": "ok"}

@app.post("/vote")
async def submit_vote(payload: Dict[str, Any], session_cookie: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name)) -> Dict[str, Any]:
    if not session_cookie:
        logger.warning("Missing session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Missing session cookie")

    if not settings.tally_function_url:
        logger.error("Missing TALLY_FUNCTION_URL")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "TALLY_FUNCTION_URL is required")

    try:
        claims = verify_session_token(session_cookie, settings.jwt_secret)
    except Exception:
        logger.warning("Invalid session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    session_id = claims.get("sid")
    if not session_id:
        logger.warning("Session cookie missing sid claim")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    vote_id = payload.get("voteId")
    option = payload.get("option")
    if not vote_id:
        logger.warning("Missing voteId")
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing voteId")
    if not option:
        logger.warning("Missing vote option")
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing option")

    try:
        redis_client = get_redis_client()
        current_vote = await redis_client.get("pulsefm:poll:current")
        if not current_vote:
            logger.warning("No current poll in redis")
            raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Vote state unavailable")
        if current_vote != vote_id:
            logger.info("VoteId mismatch", extra={"requested": vote_id, "current": current_vote})
            raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid voteId")

        options = await redis_client.hkeys(poll_tally_key(vote_id)) # type: ignore[misc]
        if not options:
            logger.warning("No poll options in redis", extra={"voteId": vote_id})
            raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Vote state unavailable")
        if option not in options:
            logger.info("Invalid option", extra={"voteId": vote_id, "option": option})
            raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid option")

        await _check_vote_rate_limits(redis_client, session_id, vote_id)

        if await has_voted_session(redis_client, vote_id, session_id):
            logger.info("Duplicate vote (redis)", extra={"voteId": vote_id, "sessionId": session_id})
            raise VoteError(status.HTTP_409_CONFLICT, "Duplicate vote")
    except VoteError:
        raise
    except Exception:
        logger.exception("Redis vote validation failed", extra={"voteId": vote_id, "sessionId": session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")

    event = {
        "voteId": vote_id,
        "option": option,
        "sessionId": session_id,
        "votedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        enqueue_json_task(settings.vote_queue_name, settings.tally_function_url, event)
    except Exception:
        logger.exception("Failed to enqueue tally task", extra={"voteId": vote_id, "sessionId": session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to enqueue vote")

    logger.info("Vote accepted", extra={"voteId": vote_id, "sessionId": session_id, "option": option})
    return {"status": "ok"}

@app.post("/downloads")
async def create_download(payload: Dict[str, Any], session_cookie: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name)) -> Dict[str, str]:
    vote_id = payload.get("voteId")
    if not vote_id:
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing voteId")

    if not session_cookie:
        logger.warning("Missing session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Missing session cookie")

    try:
        claims = verify_session_token(session_cookie, settings.jwt_secret)
    except Exception:
        logger.warning("Invalid session cookie")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    session_id = claims.get("sid")
    if not session_id:
        logger.warning("Session cookie missing sid claim")
        raise VoteError(status.HTTP_401_UNAUTHORIZED, "Invalid session cookie")

    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for downloads")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")
    await _check_download_rate_limit(redis_client, session_id, vote_id)

    storage = get_storage_client()
    bucket = storage.bucket(settings.encoded_bucket)
    blob_name = f"{settings.encoded_prefix}{vote_id}.m4a"
    blob = bucket.blob(blob_name)

    if not blob.exists():
        logger.warning("Blob not found", extra={"blob": blob_name})
        raise VoteError(status.HTTP_404_NOT_FOUND, "Audio file not found")

    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="GET",
        response_type="audio/mp4",
    )
    logger.info("Generated signed URL", extra={"voteId": vote_id})
    return {"url": url}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
