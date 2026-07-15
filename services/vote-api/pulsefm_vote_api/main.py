import logging
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, status

from pulsefm_redis.client import get_redis_client, submit_vote_atomic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote API", version="2.0.0")

_RESULT_TO_ERROR: Dict[str, tuple[int, str]] = {
    "duplicate": (status.HTTP_409_CONFLICT, "Duplicate vote"),
    "closed": (status.HTTP_409_CONFLICT, "Vote closed"),
    "not_current": (status.HTTP_400_BAD_REQUEST, "Invalid voteId"),
    "invalid_option": (status.HTTP_400_BAD_REQUEST, "Invalid option"),
    "no_state": (status.HTTP_503_SERVICE_UNAVAILABLE, "Vote state unavailable"),
}


@app.post("/vote")
async def submit_vote(
    payload: Dict[str, Any],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, str]:
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session id")

    vote_id = payload.get("voteId")
    option = payload.get("option")
    if not isinstance(vote_id, str) or not vote_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing voteId")
    if not isinstance(option, str) or not option:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing option")

    try:
        result = await submit_vote_atomic(get_redis_client(), vote_id, x_session_id, option)
    except Exception:
        logger.exception("Vote submission failed", extra={"voteId": vote_id, "sessionId": x_session_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voting temporarily unavailable (Redis unreachable)",
        )

    if result == "ok":
        logger.info("Vote counted", extra={"voteId": vote_id, "sessionId": x_session_id, "option": option})
        return {"status": "ok"}

    error_status, detail = _RESULT_TO_ERROR.get(
        result, (status.HTTP_500_INTERNAL_SERVER_ERROR, f"Unexpected vote result: {result}")
    )
    logger.info("Vote rejected", extra={"voteId": vote_id, "sessionId": x_session_id, "result": result})
    raise HTTPException(status_code=error_status, detail=detail)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
