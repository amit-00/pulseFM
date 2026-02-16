import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict

import functions_framework
from google.cloud import pubsub_v1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("PROJECT_ID", "")
HEARTBEAT_TOPIC = os.getenv("HEARTBEAT_TOPIC", "heartbeat")


@lru_cache(maxsize=1)
def _get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _success(status: str, extra: Dict[str, Any] | None = None, code: int = 200):
    payload = {"status": status}
    if extra:
        payload.update(extra)
    return payload, code


def _publish_json(payload: Dict[str, Any]) -> None:
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID is required")
    path = _get_publisher().topic_path(PROJECT_ID, HEARTBEAT_TOPIC)
    _get_publisher().publish(path, data=json.dumps(payload).encode("utf-8"))


@functions_framework.http
def heartbeat_ingress(request):
    if request.method != "POST":
        logger.warning("Invalid method", extra={"method": request.method})
        return _success("method_not_allowed", code=405)

    session_id = request.headers.get("X-Session-Id")
    if not session_id:
        logger.warning("Missing session id header")
        return _success("missing_session_id", code=400)

    try:
        _publish_json({"sessionId": session_id})
    except Exception:
        logger.exception("Failed to publish heartbeat", extra={"sessionId": session_id})
        return _success("error", code=500)

    return _success("ok")
