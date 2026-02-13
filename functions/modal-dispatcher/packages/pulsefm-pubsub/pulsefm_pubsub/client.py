import base64
import json
import os
from functools import lru_cache
from typing import Any, Mapping

from google.cloud import pubsub_v1


class PubSubClientError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _resolve_project_id(project_id: str | None) -> str:
    resolved = project_id or os.getenv("PROJECT_ID", "")
    if not resolved:
        raise PubSubClientError("project_id is required")
    return resolved


def topic_path(project_id: str | None, topic: str) -> str:
    project_id = _resolve_project_id(project_id)
    if not topic:
        raise PubSubClientError("topic is required")
    return get_publisher().topic_path(project_id, topic)


def publish_json(
    project_id: str | None,
    topic: str,
    payload: Mapping[str, Any],
    attributes: Mapping[str, str] | None = None,
) -> None:
    data = json.dumps(payload).encode("utf-8")
    path = topic_path(project_id, topic)
    if attributes:
        get_publisher().publish(path, data=data, **attributes)
    else:
        get_publisher().publish(path, data=data)


def decode_pubsub_json(payload: Mapping[str, Any]) -> dict[str, Any]:
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
