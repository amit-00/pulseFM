import base64
import json
import logging
import os
from functools import lru_cache
from typing import Any, Mapping

import functions_framework
import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HEARTBEAT_TTL_SECONDS = int(os.getenv("HEARTBEAT_TTL_SECONDS", "30"))

HEARTBEAT_LUA = """
local session_key = KEYS[1]
local active_key = KEYS[2]
local ttl = tonumber(ARGV[1])

redis.call("SET", session_key, "1", "EX", ttl)
redis.call("SET", active_key, "1", "EX", ttl)

return "ok"
"""


@lru_cache(maxsize=1)
def _get_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "")
    port = int(os.getenv("REDIS_PORT", "6379"))
    if not host:
        raise ValueError("REDIS_HOST is required")
    return redis.Redis(host=host, port=port, decode_responses=True)


def _decode_pubsub_json(payload: Mapping[str, Any]) -> dict[str, Any]:
    message = payload.get("message") or {}
    data = message.get("data")
    if not data:
        return {}
    try:
        raw = base64.b64decode(data)
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        decoded = json.loads(data)
    if isinstance(decoded, dict):
        return decoded
    return {"data": decoded}


def _session_key(session_id: str) -> str:
    return f"pulsefm:heartbeat:session:{session_id}"


@functions_framework.cloud_event
def heartbeat_receiver(event):
    payload = _decode_pubsub_json(event.data or {})
    session_id = payload.get("sessionId")
    if not session_id:
        logger.warning("Missing sessionId in heartbeat message")
        return

    ttl_seconds = max(1, int(HEARTBEAT_TTL_SECONDS))
    try:
        client = _get_redis_client()
        client.eval(
            HEARTBEAT_LUA,
            2,
            _session_key(session_id),
            "pulsefm:heartbeat:active",
            ttl_seconds,
        )
    except Exception:
        logger.exception("Failed to update heartbeat keys", extra={"sessionId": session_id})
        raise

    logger.info("Heartbeat refreshed", extra={"sessionId": session_id, "ttlSeconds": ttl_seconds})
