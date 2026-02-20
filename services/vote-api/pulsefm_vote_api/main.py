import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, status

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


async def _validate_vote(vote_id: str, option: str, session_id: str) -> None:
    try:
        redis_client = get_redis_client()

        snapshot = await get_playback_current_snapshot(redis_client)
        if not snapshot:
            logger.warning("No playback snapshot in redis")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Vote state unavailable")

        poll = snapshot.get("poll") or {}
        current_vote = poll.get("voteId")
        current_status = poll.get("status")

        if not current_vote:
            logger.warning("No current poll in playback snapshot")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Vote state unavailable")
        if current_vote != vote_id:
            logger.info("VoteId mismatch", extra={"requested": vote_id, "current": current_vote})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid voteId")
        if current_status != "OPEN":
            logger.info("Vote rejected because poll is closed", extra={"voteId": vote_id, "status": current_status})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vote closed")

        options = await redis_client.hkeys(poll_tally_key(vote_id))  # type: ignore[misc]
        if not options:
            logger.warning("No poll options in redis", extra={"voteId": vote_id})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Vote state unavailable")
        if option not in options:
            logger.info("Invalid option", extra={"voteId": vote_id, "option": option})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid option")

        if await has_voted_session(redis_client, vote_id, session_id):
            logger.info("Duplicate vote (redis)", extra={"voteId": vote_id, "sessionId": session_id})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate vote")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Redis vote validation failed", extra={"voteId": vote_id, "sessionId": session_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")


@app.post("/vote")
async def submit_vote(
    payload: Dict[str, Any],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, Any]:
    if not x_session_id:
        logger.warning("Missing session id header")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session id")

    if not settings.tally_function_url:
        logger.error("Missing TALLY_FUNCTION_URL")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TALLY_FUNCTION_URL is required")

    vote_id = payload.get("voteId")
    option = payload.get("option")
    if not vote_id:
        logger.warning("Missing voteId")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing voteId")
    if not option:
        logger.warning("Missing vote option")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing option")

    await _validate_vote(vote_id, option, x_session_id)

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enqueue vote")

    logger.info("Vote accepted", extra={"voteId": vote_id, "sessionId": x_session_id, "option": option})
    return {"status": "ok"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
