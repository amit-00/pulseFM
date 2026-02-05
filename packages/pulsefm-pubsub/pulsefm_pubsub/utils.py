import base64
import json
import os
from typing import Any, Dict, Tuple

from google.cloud import pubsub_v1


def decode_pubsub_push(body: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    message = body.get("message")
    if not message:
        raise ValueError("Missing Pub/Sub message")

    data_b64 = message.get("data", "")
    if not data_b64:
        payload = {}
    else:
        payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))

    attributes = message.get("attributes") or {}
    return payload, attributes


def publish_json(topic_name: str, payload: Dict[str, Any], attributes: Dict[str, str] | None = None) -> str:
    project_id = os.getenv("PROJECT_ID", "")
    if not project_id:
        raise ValueError("PROJECT_ID is required")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, data=data, attributes=attributes or {})
    return future.result()
