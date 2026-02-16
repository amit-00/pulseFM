import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict

import functions_framework
import redis
from google.cloud import pubsub_v1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TALLY_TOPIC = os.getenv("TALLY_TOPIC", "tally")
PROJECT_ID = os.getenv("PROJECT_ID", "")

VOTE_LUA = """
local voted_key = KEYS[1]
local tally_key = KEYS[2]
local session_id = ARGV[1]
local option = ARGV[2]

local added = redis.call("SADD", voted_key, session_id)
if added == 1 then
  redis.call("HINCRBY", tally_key, option, 1)
  return 1
end
return 0
"""


@lru_cache(maxsize=1)
def _get_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "")
    port = int(os.getenv("REDIS_PORT", "6379"))
    if not host:
        raise ValueError("REDIS_HOST is required")
    return redis.Redis(host=host, port=port, decode_responses=True)


@lru_cache(maxsize=1)
def _get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _success(status: str, extra: Dict[str, Any] | None = None, code: int = 200):
    payload = {"status": status}
    if extra:
        payload.update(extra)
    return payload, code


def _playback_current_key() -> str:
    return "pulsefm:playback:current"


def _poll_tally_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:tally"


def _poll_voted_key(vote_id: str) -> str:
    return f"pulsefm:poll:{vote_id}:voted"


def _get_playback_current_snapshot(client: redis.Redis) -> dict | None:
    raw = client.get(_playback_current_key())
    if not raw:
        return None
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return None


def _record_vote_atomic(client: redis.Redis, vote_id: str, session_id: str, option: str) -> bool:
    result = client.eval(
        VOTE_LUA,
        2,
        _poll_voted_key(vote_id),
        _poll_tally_key(vote_id),
        session_id,
        option,
    )
    return int(result) == 1  # type: ignore[arg-type]


def _publish_json(topic: str, payload: Dict[str, Any]) -> None:
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID is required")
    path = _get_publisher().topic_path(PROJECT_ID, topic)
    _get_publisher().publish(path, data=json.dumps(payload).encode("utf-8"))


@functions_framework.http
def tally_function(request):
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
        redis_client = _get_redis_client()
        snapshot = _get_playback_current_snapshot(redis_client)
        current_vote_id = (snapshot or {}).get("poll", {}).get("voteId")
        if current_vote_id != vote_id:
            logger.info("Vote not current", extra={"voteId": vote_id, "currentVoteId": current_vote_id})
            return _success("vote_not_open")

        option_exists = redis_client.hexists(_poll_tally_key(vote_id), option)
        if not option_exists:
            logger.info("Invalid option", extra={"voteId": vote_id, "option": option})
            return _success("invalid_option")

        added = _record_vote_atomic(redis_client, vote_id, session_id, option)
    except Exception:
        logger.exception("Redis tally update failed", extra={"voteId": vote_id, "sessionId": session_id})
        return _success("error", code=500)

    if not added:
        logger.info("Duplicate vote (redis)", extra={"voteId": vote_id, "sessionId": session_id})
        return _success("duplicate")

    logger.info("Tally applied", extra={"voteId": vote_id, "sessionId": session_id, "option": option})
    try:
        _publish_json(TALLY_TOPIC, {"voteId": vote_id})
    except Exception:
        logger.exception("Failed to publish tally event", extra={"voteId": vote_id})
    return _success("ok")
