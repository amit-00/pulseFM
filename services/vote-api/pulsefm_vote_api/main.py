import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Cookie, FastAPI, HTTPException, Response, status
from google.cloud.firestore import AsyncClient, AsyncTransaction, SERVER_TIMESTAMP, async_transactional
from google.cloud.storage import Client as StorageClient

from pulsefm_auth.session import issue_session_token, verify_session_token
from pulsefm_tasks.client import enqueue_json_task

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


async def _get_vote_state(db: AsyncClient) -> Dict[str, Any]:
    doc_ref = db.collection(settings.firestore_vote_state_collection).document("current")
    doc = await doc_ref.get()
    if not doc.exists:
        raise VoteError(status.HTTP_404_NOT_FOUND, "Vote window not initialized")
    return doc.to_dict() or {}


async def _get_vote_window(db: AsyncClient, vote_id: str) -> Dict[str, Any]:
    if not vote_id:
        raise VoteError(status.HTTP_404_NOT_FOUND, "Vote window not initialized")
    doc_ref = db.collection(settings.firestore_vote_windows_collection).document(vote_id)
    doc = await doc_ref.get()
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


def _vote_doc_id(vote_id: str, session_id: str) -> str:
    return f"{vote_id}:{session_id}"



@app.post("/session")
def create_session(response: Response) -> Dict[str, str]:
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

    db = get_firestore_client()
    heartbeat_ref = db.collection(settings.firestore_heartbeats_collection).document(session_id)
    await heartbeat_ref.set({
        "sessionId": session_id,
        "heartbeatAt": SERVER_TIMESTAMP,
    })

    return {"status": "ok"}

@app.get("/window")
async def get_window() -> Dict[str, Any]:
    db = get_firestore_client()
    state = await _get_vote_state(db)
    logger.info("Fetched vote window", extra={"voteId": state.get("voteId"), "status": state.get("status")})
    return {
        "voteId": state.get("voteId"),
        "status": state.get("status"),
        "startAt": _serialize_timestamp(state.get("startAt")),
        "endAt": _serialize_timestamp(state.get("endAt")),
        "options": state.get("options", []),
        "tallies": state.get("tallies", {}),
        "version": state.get("version"),
    }


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

    option = payload.get("option")
    if not option:
        logger.warning("Missing vote option")
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing option")

    db = get_firestore_client()
    state = await _get_vote_state(db)
    if state.get("status") != "OPEN":
        logger.info("Vote window closed", extra={"voteId": state.get("voteId"), "status": state.get("status")})
        raise VoteError(status.HTTP_409_CONFLICT, "Voting window is closed")

    window = await _get_vote_window(db, state.get("voteId") or "")
    options = window.get("options") or []
    if option not in options:
        logger.info("Invalid option", extra={"voteId": state.get("voteId"), "option": option})
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid option")

    end_at = _parse_timestamp(state.get("endAt"))
    now = datetime.now(timezone.utc)
    if now >= end_at:
        logger.info("Vote window ended", extra={"voteId": state.get("voteId")})
        raise VoteError(status.HTTP_409_CONFLICT, "Voting window has ended")

    vote_id = state.get("voteId") or ""
    vote_doc_id = _vote_doc_id(vote_id, session_id)
    votes_ref = db.collection(settings.firestore_votes_collection)

    @async_transactional
    async def _create_vote(transaction: AsyncTransaction) -> bool:
        vote_doc = votes_ref.document(vote_doc_id)
        snapshot = await vote_doc.get(transaction=transaction)
        if snapshot.exists:
            return False
        transaction.set(vote_doc, {
            "voteId": vote_id,
            "sessionId": session_id,
            "option": option,
            "votedAt": SERVER_TIMESTAMP,
            "counted": False,
        })
        return True

    transaction = db.transaction()
    created = await _create_vote(transaction)
    if not created:
        logger.info("Duplicate vote", extra={"voteId": vote_id, "sessionId": session_id})
        raise VoteError(status.HTTP_409_CONFLICT, "Duplicate vote")

    event = {
        "voteId": vote_id,
        "option": option,
        "sessionId": session_id,
        "votedAt": now.isoformat(),
        "version": state.get("version"),
    }
    try:
        enqueue_json_task(settings.vote_queue_name, settings.tally_function_url, event)
    except Exception:
        await votes_ref.document(vote_doc_id).delete()
        logger.exception("Failed to enqueue tally task", extra={"voteId": vote_id, "sessionId": session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to enqueue vote")

    logger.info("Vote accepted", extra={"voteId": vote_id, "sessionId": session_id, "option": option})
    return {"status": "ok"}


@app.post("/downloads")
def create_download(payload: Dict[str, Any]) -> Dict[str, str]:
    vote_id = payload.get("voteId")
    if not vote_id:
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing voteId")

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
