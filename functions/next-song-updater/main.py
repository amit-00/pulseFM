from __future__ import annotations

import logging
import os
import json
from functools import lru_cache
from typing import Any

import functions_framework
from google.cloud import firestore
from google.cloud import pubsub_v1
import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_BUCKET = os.getenv("TARGET_BUCKET", "pulsefm-generated-songs")
ENCODED_PREFIX = os.getenv("ENCODED_PREFIX", "encoded/")
STATIONS_COLLECTION = os.getenv("STATIONS_COLLECTION", "stations")
STATION_DOC_ID = os.getenv("STATION_DOC_ID", "main")
SONGS_COLLECTION = os.getenv("SONGS_COLLECTION", "songs")
STUBBED_VOTE_ID = "stubbed"
PROJECT_ID = os.getenv("PROJECT_ID", "")
PLAYBACK_EVENTS_TOPIC = os.getenv("PLAYBACK_EVENTS_TOPIC", "playback")
PLAYBACK_CURRENT_KEY = "pulsefm:playback:current"


class RetryableError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _get_firestore_client() -> firestore.Client:
    return firestore.Client()


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


def _publish_next_song_changed(vote_id: str, duration_ms: int) -> None:
    if not PROJECT_ID:
        raise ValueError("PROJECT_ID is required")
    topic_path = _get_publisher().topic_path(PROJECT_ID, PLAYBACK_EVENTS_TOPIC)
    payload = {
        "event": "NEXT-SONG-CHANGED",
        "voteId": vote_id,
        "durationMs": duration_ms,
    }
    _get_publisher().publish(topic_path, data=json.dumps(payload).encode("utf-8"))


def _update_redis_next_song(vote_id: str, duration_ms: int) -> str:
    client = _get_redis_client()
    raw = client.get(PLAYBACK_CURRENT_KEY)
    if not raw:
        raise RetryableError("playback snapshot missing")
    try:
        snapshot = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise RetryableError("playback snapshot invalid JSON") from exc

    if not isinstance(snapshot, dict):
        raise RetryableError("playback snapshot invalid")

    next_song = snapshot.get("nextSong")
    if not isinstance(next_song, dict):
        next_song = {}

    current_next_vote_id = next_song.get("voteId")
    if current_next_vote_id not in (STUBBED_VOTE_ID, vote_id):
        return "skip_snapshot_not_stubbed"

    next_song["voteId"] = vote_id
    next_song["durationMs"] = duration_ms
    snapshot["nextSong"] = next_song

    ttl = client.ttl(PLAYBACK_CURRENT_KEY)
    payload = json.dumps(snapshot, separators=(",", ":"))
    if ttl and int(ttl) > 0:
        client.set(PLAYBACK_CURRENT_KEY, payload, ex=int(ttl))
    else:
        client.set(PLAYBACK_CURRENT_KEY, payload)
    return "updated"


@firestore.transactional
def _update_next_if_stubbed(
    transaction: firestore.Transaction,
    station_ref: firestore.DocumentReference,
    song_ref: firestore.DocumentReference,
    vote_id: str,
) -> dict[str, Any]:
    station_snapshot = station_ref.get(transaction=transaction)
    if not station_snapshot.exists:
        logger.warning("stations/main does not exist")
        return {"result": "missing_station"}

    station = station_snapshot.to_dict() or {}
    next_song = station.get("next") or {}
    if next_song.get("voteId") != STUBBED_VOTE_ID:
        if next_song.get("voteId") == vote_id:
            duration_ms = next_song.get("durationMs") or next_song.get("duration")
            if isinstance(duration_ms, int) and duration_ms > 0:
                return {"result": "already_updated", "durationMs": duration_ms}
        return {"result": "skip_not_stubbed"}

    song_snapshot = song_ref.get(transaction=transaction)
    if not song_snapshot.exists:
        raise RetryableError(f"songs/{vote_id} does not exist yet")

    song = song_snapshot.to_dict() or {}
    duration_ms: Any = song.get("durationMs")
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        raise RetryableError(f"songs/{vote_id}.durationMs is missing or invalid")

    transaction.update(
        station_ref,
        {
            "next.voteId": vote_id,
            "next.duration": duration_ms,
            "next.durationMs": duration_ms,
        },
    )
    return {"result": "updated", "durationMs": duration_ms}


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

    db = _get_firestore_client()
    station_ref = db.collection(STATIONS_COLLECTION).document(STATION_DOC_ID)
    song_ref = db.collection(SONGS_COLLECTION).document(vote_id)

    try:
        tx = db.transaction()
        tx_result = _update_next_if_stubbed(tx, station_ref, song_ref, vote_id)
    except RetryableError:
        logger.exception("Retryable update failure", extra={"voteId": vote_id})
        raise
    except Exception:
        logger.exception("Failed to update station next song", extra={"voteId": vote_id})
        raise

    result = str(tx_result.get("result"))
    duration_ms = tx_result.get("durationMs")
    if result in {"updated", "already_updated"}:
        if not isinstance(duration_ms, int) or duration_ms <= 0:
            raise RetryableError("durationMs missing for redis update")
        try:
            redis_result = _update_redis_next_song(vote_id, duration_ms)
        except Exception:
            logger.exception("Failed to update playback snapshot in redis", extra={"voteId": vote_id})
            raise
        try:
            _publish_next_song_changed(vote_id, duration_ms)
        except Exception:
            logger.exception("Failed to publish next-song-changed", extra={"voteId": vote_id})
            raise
        logger.info(
            "Updated station and playback snapshot for next song",
            extra={"voteId": vote_id, "durationMs": duration_ms, "result": result, "redisResult": redis_result},
        )
        return

    logger.info("Handled encoded object", extra={"voteId": vote_id, "result": result})
