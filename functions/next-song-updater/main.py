from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

import functions_framework
from google.api_core import exceptions as gax_exceptions
from google.cloud import firestore
from google.cloud import tasks_v2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_BUCKET = os.getenv("TARGET_BUCKET", "pulsefm-generated-songs")
ENCODED_PREFIX = os.getenv("ENCODED_PREFIX", "encoded/")
SONGS_COLLECTION = os.getenv("SONGS_COLLECTION", "songs")
PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "")
PLAYBACK_QUEUE_NAME = os.getenv("PLAYBACK_QUEUE_NAME", "playback-queue")
PLAYBACK_SERVICE_URL = os.getenv("PLAYBACK_SERVICE_URL", "")
TASKS_OIDC_SERVICE_ACCOUNT = os.getenv("TASKS_OIDC_SERVICE_ACCOUNT", "")
STUBBED_VOTE_ID = "stubbed"


class RetryableError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _get_firestore_client() -> firestore.Client:
    return firestore.Client()


@lru_cache(maxsize=1)
def _get_tasks_client() -> tasks_v2.CloudTasksClient:
    return tasks_v2.CloudTasksClient()


def _normalize_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("/") else f"{prefix}/"


def _extract_vote_id(object_name: str) -> str | None:
    normalized_prefix = _normalize_prefix(ENCODED_PREFIX)
    if not object_name.startswith(normalized_prefix):
        return None

    leaf = object_name[len(normalized_prefix):]
    if "/" in leaf or not leaf.endswith(".m4a"):
        return None

    vote_id = leaf[:-4]
    if not vote_id or vote_id == STUBBED_VOTE_ID:
        return None
    return vote_id


def _load_duration_ms(vote_id: str) -> int:
    doc = _get_firestore_client().collection(SONGS_COLLECTION).document(vote_id).get()
    if not doc.exists: # type: ignore[union-attr]
        raise RetryableError(f"songs/{vote_id} does not exist yet")
    data = doc.to_dict() or {} # type: ignore[attr-defined]
    duration_ms = data.get("durationMs")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise RetryableError(f"songs/{vote_id}.durationMs is missing or invalid")
    return duration_ms


def _build_task_id(vote_id: str, duration_ms: int) -> str:
    return f"next-song-replace-{vote_id}-{duration_ms}"


def _enqueue_replace_next_task(vote_id: str, duration_ms: int) -> None:
    if not PROJECT_ID or not LOCATION:
        raise ValueError("PROJECT_ID and LOCATION are required")
    if not PLAYBACK_SERVICE_URL:
        raise ValueError("PLAYBACK_SERVICE_URL is required")

    client = _get_tasks_client()
    parent = client.queue_path(PROJECT_ID, LOCATION, PLAYBACK_QUEUE_NAME)
    task = {
        "name": client.task_path(PROJECT_ID, LOCATION, PLAYBACK_QUEUE_NAME, _build_task_id(vote_id, duration_ms)),
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": PLAYBACK_SERVICE_URL.rstrip("/") + "/next/replace-if-stubbed",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"voteId": vote_id, "durationMs": duration_ms}).encode("utf-8"),
        },
    }
    if TASKS_OIDC_SERVICE_ACCOUNT:
        task["http_request"]["oidc_token"] = {
            "service_account_email": TASKS_OIDC_SERVICE_ACCOUNT,
        }

    try:
        client.create_task(request={"parent": parent, "task": task})
    except gax_exceptions.AlreadyExists:
        logger.info("Replace-next task already exists", extra={"voteId": vote_id, "durationMs": duration_ms})


@functions_framework.cloud_event
def next_song_updater(event):
    payload = event.data or {}
    bucket = payload.get("bucket")
    object_name = payload.get("name")

    if not isinstance(bucket, str) or not isinstance(object_name, str):
        logger.warning("Invalid CloudEvent payload")
        return

    if bucket != TARGET_BUCKET:
        logger.info("Ignoring non-target bucket object", extra={"bucket": bucket, "name": object_name})
        return

    vote_id = _extract_vote_id(object_name)
    if not vote_id:
        logger.info("Ignoring non-encoded object", extra={"name": object_name})
        return

    try:
        duration_ms = _load_duration_ms(vote_id)
        _enqueue_replace_next_task(vote_id, duration_ms)
    except RetryableError:
        logger.exception("Retryable next-song enqueue failure", extra={"voteId": vote_id})
        raise
    except Exception:
        logger.exception("Failed to enqueue replace-next task", extra={"voteId": vote_id})
        raise

    logger.info("Enqueued replace-next task", extra={"voteId": vote_id, "durationMs": duration_ms})
