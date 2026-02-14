import logging
import os
from typing import Any, Dict

import functions_framework

from pulsefm_pubsub.client import publish_json
from pulsefm_redis.client import get_playback_current_snapshot, get_redis_client, poll_tally_key, record_vote_atomic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

redis_client = get_redis_client()
TALLY_TOPIC = os.getenv("TALLY_TOPIC", "tally")
PROJECT_ID = os.getenv("PROJECT_ID", "")


def _success(status: str, extra: Dict[str, Any] | None = None, code: int = 200):
    payload = {"status": status}
    if extra:
        payload.update(extra)
    return payload, code


@functions_framework.http
async def tally_function(request):
    if request.method != "POST":
        logger.warning("Invalid method", extra={"method": request.method})
        return _success("method_not_allowed", code=405)

    payload = request.get_json(silent=True) or {}
    vote_id = payload.get("voteId")
    session_id = payload.get("sessionId")
    option = payload.get("option")

    if not vote_id or not session_id or not option:
        logger.warning("Missing fields", extra={"voteId": vote_id, "sessionId": session_id})
        return _success("missing_fields")

    try:
        snapshot = await get_playback_current_snapshot(redis_client)
        current_vote_id = (snapshot or {}).get("poll", {}).get("voteId")
        if current_vote_id != vote_id:
            logger.info("Vote not current", extra={"voteId": vote_id, "currentVoteId": current_vote_id})
            return _success("vote_not_open")

        option_exists = await redis_client.hexists(poll_tally_key(vote_id), option) # type: ignore[misc]
        if not option_exists:
            logger.info("Invalid option", extra={"voteId": vote_id, "option": option})
            return _success("invalid_option")

        added = await record_vote_atomic(redis_client, vote_id, session_id, option)
    except Exception:
        logger.exception("Redis tally update failed", extra={"voteId": vote_id, "sessionId": session_id})
        return _success("error", code=500)

    if not added:
        logger.info("Duplicate vote (redis)", extra={"voteId": vote_id, "sessionId": session_id})
        return _success("duplicate")

    if added:
        logger.info("Tally applied", extra={"voteId": vote_id, "sessionId": session_id, "option": option})
        try:
            publish_json(PROJECT_ID, TALLY_TOPIC, {"voteId": vote_id})
        except Exception:
            logger.exception("Failed to publish tally event", extra={"voteId": vote_id})
    else:
        logger.info("Tally not applied", extra={"voteId": vote_id, "sessionId": session_id})
    return _success("ok")
