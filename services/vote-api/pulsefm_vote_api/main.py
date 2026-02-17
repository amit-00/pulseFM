import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, status
from google.cloud.storage import Client as StorageClient

from pulsefm_tasks.client import enqueue_json_task
from pulsefm_redis.client import (
    get_playback_current_snapshot,
    get_redis_client,
    has_voted_session,
    poll_tally_key,
)

from pulsefm_vote_api.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote API", version="1.0.0")
_storage: StorageClient | None = None


def get_storage_client() -> StorageClient:
    global _storage
    if _storage is None:
        _storage = StorageClient()
    return _storage


class VoteError(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

@app.post("/vote")
async def submit_vote(
    payload: Dict[str, Any],
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, Any]:
    if not x_session_id:
        logger.warning("Missing session id header")
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing session id")

    if not settings.tally_function_url:
        logger.error("Missing TALLY_FUNCTION_URL")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "TALLY_FUNCTION_URL is required")

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
        snapshot = await get_playback_current_snapshot(redis_client)
        if not snapshot:
            logger.warning("No playback snapshot in redis")
            raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Vote state unavailable")
        current_vote = (snapshot.get("poll") or {}).get("voteId")
        current_status = (snapshot.get("poll") or {}).get("status")
        if not current_vote:
            logger.warning("No current poll in playback snapshot")
            raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Vote state unavailable")
        if current_vote != vote_id:
            logger.info("VoteId mismatch", extra={"requested": vote_id, "current": current_vote})
            raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid voteId")
        if current_status != "OPEN":
            logger.info("Vote rejected because poll is closed", extra={"voteId": vote_id, "status": current_status})
            raise VoteError(status.HTTP_409_CONFLICT, "Vote closed")

        options = await redis_client.hkeys(poll_tally_key(vote_id)) # type: ignore[misc]
        if not options:
            logger.warning("No poll options in redis", extra={"voteId": vote_id})
            raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Vote state unavailable")
        if option not in options:
            logger.info("Invalid option", extra={"voteId": vote_id, "option": option})
            raise VoteError(status.HTTP_400_BAD_REQUEST, "Invalid option")

        if await has_voted_session(redis_client, vote_id, x_session_id):
            logger.info("Duplicate vote (redis)", extra={"voteId": vote_id, "sessionId": x_session_id})
            raise VoteError(status.HTTP_409_CONFLICT, "Duplicate vote")
    except VoteError:
        raise
    except Exception:
        logger.exception("Redis vote validation failed", extra={"voteId": vote_id, "sessionId": x_session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")

    event = {
        "voteId": vote_id,
        "option": option,
        "sessionId": x_session_id,
        "votedAt": datetime.now(timezone.utc).isoformat(),
    }
    try:
        enqueue_json_task(settings.vote_queue_name, settings.tally_function_url, event)
    except Exception:
        logger.exception("Failed to enqueue tally task", extra={"voteId": vote_id, "sessionId": x_session_id})
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to enqueue vote")

    logger.info("Vote accepted", extra={"voteId": vote_id, "sessionId": x_session_id, "option": option})
    return {"status": "ok"}

@app.post("/downloads")
async def create_download(
    payload: Dict[str, Any],
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, str]:
    vote_id = payload.get("voteId")
    if not vote_id:
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing voteId")

    if not x_session_id:
        logger.warning("Missing session id header")
        raise VoteError(status.HTTP_400_BAD_REQUEST, "Missing session id")

    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for downloads")
        raise VoteError(status.HTTP_500_INTERNAL_SERVER_ERROR, "Redis unavailable")

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
