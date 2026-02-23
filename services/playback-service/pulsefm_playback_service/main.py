import logging
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import uuid

from fastapi import FastAPI, HTTPException, status
from google.cloud import firestore
from google.cloud.firestore import AsyncClient, AsyncTransaction, async_transactional, SERVER_TIMESTAMP

from pulsefm_descriptors.data import get_descriptor_keys
from pulsefm_pubsub.client import publish_json
from pulsefm_redis.client import (
    get_playback_current_snapshot,
    get_poll_tallies,
    get_redis_client,
    init_poll_open_atomic,
    playback_current_key,
    set_playback_current_snapshot,
    set_playback_poll_status,
)
from pulsefm_tasks.client import enqueue_json_task_with_delay

from pulsefm_playback_service.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_STARTUP_DELAY_SECONDS = 30
VOTE_CLOSE_LEAD_SECONDS = 60
DEFAULT_SNAPSHOT_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_epoch_ms(value: Any) -> int | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


def _remaining_delay_seconds(ends_at: Any) -> int | None:
    if not ends_at:
        return None
    try:
        parsed = _parse_timestamp(ends_at)
    except ValueError:
        return None
    delta = (parsed - _utc_now()).total_seconds()
    return max(0, int(delta))


def _tick_url() -> str:
    return settings.playback_tick_url.rstrip("/") + "/tick"


def _vote_close_url() -> str:
    return settings.playback_tick_url.rstrip("/") + "/vote/close"


def _validate_tick_version(payload: Dict[str, Any]) -> int:
    version_raw = payload.get("version")
    if version_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version is required")
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be an integer")
    if version <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be positive")
    return version


def _build_tick_task_id(vote_id: str | None, ends_at: datetime | None, version: int | None = None) -> str:
    suffix = vote_id or ""
    timestamp = str(int(ends_at.timestamp())) if ends_at else ""
    version_suffix = str(version) if version is not None else ""
    return f"playback-{suffix}-{timestamp}-{version_suffix}"


def _build_vote_close_task_id(vote_id: str, version: int) -> str:
    return f"vote-close-{vote_id}-{version}"


# ---------------------------------------------------------------------------
# SongRotationResult
# ---------------------------------------------------------------------------


@dataclass
class SongRotationResult:
    start_at: datetime
    ends_at: datetime
    duration_ms: int
    vote_id: str
    next_vote_id: str
    next_duration_ms: int
    next_stubbed: bool
    version: int


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_db: AsyncClient | None = None


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db


@asynccontextmanager
async def lifespan(a: FastAPI):
    await _ensure_playback_tick_scheduled()
    yield


app = FastAPI(title="PulseFM Playback Service", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------


async def _get_station_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(settings.stations_collection).document("main").get()
    return doc.to_dict() if doc.exists else None


async def _get_current_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(settings.vote_state_collection).document("current").get()
    return doc.to_dict() if doc.exists else None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


async def _ensure_playback_tick_scheduled() -> None:
    if not settings.playback_tick_url:
        logger.warning("PLAYBACK_TICK_URL not set; skipping startup scheduling")
        return
    db = get_firestore_client()
    station = await _get_station_state(db)
    if not station:
        logger.warning("stations/main missing; skipping startup scheduling")
        return
    ends_at = station.get("endAt")
    vote_id = station.get("voteId")
    current_version = int(station.get("version") or 0)
    next_version = current_version + 1
    delay_seconds = _remaining_delay_seconds(ends_at) or DEFAULT_STARTUP_DELAY_SECONDS
    parsed_end_at = None
    if ends_at:
        try:
            parsed_end_at = _parse_timestamp(ends_at)
        except ValueError:
            parsed_end_at = None
    task_id = _build_tick_task_id(vote_id, parsed_end_at, next_version)
    enqueue_json_task_with_delay(
        settings.playback_queue,
        _tick_url(),
        {"version": next_version},
        delay_seconds,
        task_id=task_id,
        ignore_already_exists=True,
    )
    logger.info(
        "Startup tick scheduled",
        extra={"voteId": vote_id, "delaySeconds": delay_seconds, "version": next_version},
    )


# ---------------------------------------------------------------------------
# Vote building
# ---------------------------------------------------------------------------


def _build_vote(vote_id: str, start_at: datetime, duration_ms: int, options: list[str], version: int) -> Dict[str, Any]:
    end_at = start_at + timedelta(milliseconds=duration_ms)
    return {
        "voteId": vote_id,
        "status": "OPEN",
        "startAt": start_at,
        "durationMs": duration_ms,
        "endAt": end_at,
        "options": options,
        "tallies": {option: 0 for option in options},
        "version": version,
        "createdAt": SERVER_TIMESTAMP,
    }


def _get_window_options() -> list[str]:
    if settings.vote_options:
        return settings.vote_options
    options = get_descriptor_keys()
    if len(options) < settings.options_per_window:
        raise ValueError("Not enough descriptor options to sample window choices")
    return random.sample(options, settings.options_per_window)


def _pick_winner(tallies: Dict[str, Any]) -> str | None:
    if not tallies:
        return None
    max_votes = max(tallies.values())
    tied = [option for option, count in tallies.items() if count == max_votes]
    return random.choice(tied) if tied else None


# ---------------------------------------------------------------------------
# Publishing helpers
# ---------------------------------------------------------------------------


def _publish_vote_event(
    event: str,
    vote_id: str,
    winner_option: str | None = None,
    end_at_ms: int | None = None,
) -> None:
    payload: Dict[str, Any] = {"event": event, "voteId": vote_id}
    if winner_option is not None:
        payload["winnerOption"] = winner_option
    if end_at_ms is not None:
        payload["endAt"] = end_at_ms
    publish_json(settings.project_id or None, settings.vote_events_topic, payload)


def _publish_playback_event(event: str, payload: Dict[str, Any]) -> None:
    event_payload = {"event": event, **payload}
    publish_json(settings.project_id or None, settings.playback_events_topic, event_payload)


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


async def _update_playback_next_song_snapshot(vote_id: str, duration_ms: int) -> bool:
    client = get_redis_client()
    snapshot = await get_playback_current_snapshot(client)
    if not snapshot:
        raise ValueError("playback snapshot missing")

    next_song = snapshot.get("nextSong")
    if not isinstance(next_song, dict):
        next_song = {}

    desired_duration = int(duration_ms)
    if next_song.get("voteId") == vote_id and _parse_int(next_song.get("durationMs")) == desired_duration:
        return False

    next_song["voteId"] = vote_id
    next_song["durationMs"] = desired_duration
    snapshot["nextSong"] = next_song

    ttl = await client.ttl(playback_current_key())  # type: ignore[misc]
    effective_ttl = int(ttl) if ttl and int(ttl) > 0 else DEFAULT_SNAPSHOT_TTL_SECONDS
    await set_playback_current_snapshot(client, snapshot, effective_ttl)
    return True


async def _reconcile_next_song_snapshot(result: Dict[str, Any]) -> bool:
    vote_id = result.get("voteId")
    duration_ms = result.get("durationMs")
    if not isinstance(vote_id, str) or not vote_id:
        return False
    if not isinstance(duration_ms, int) or duration_ms <= 0:
        return False
    return await _update_playback_next_song_snapshot(vote_id, duration_ms)


async def _update_redis_on_open(
    vote_id: str,
    start_at: datetime,
    end_at: datetime,
    duration_ms: int,
    options: list[str],
    snapshot: Dict[str, Any],
) -> None:
    client = get_redis_client()
    current_ttl_seconds = max(1, int(duration_ms / 1000))
    state_ttl_seconds = max(1, int((end_at + timedelta(hours=1) - _utc_now()).total_seconds()))

    await init_poll_open_atomic(
        client,
        vote_id,
        snapshot,
        current_ttl_seconds,
        state_ttl_seconds,
        options,
    )


# ---------------------------------------------------------------------------
# Vote operations
# ---------------------------------------------------------------------------


async def _close_vote(db: AsyncClient, state: Dict[str, Any]) -> Dict[str, Any]:
    vote_id = state.get("voteId")
    if not vote_id:
        raise ValueError("voteId missing from voteState/current")
    try:
        tallies = await get_poll_tallies(get_redis_client(), vote_id)
    except Exception:
        logger.exception("Failed to load tallies from Redis", extra={"voteId": vote_id})
        raise
    if not tallies:
        tallies = {option: 0 for option in (state.get("options") or [])}
    winner_option = _pick_winner(tallies)

    window_doc = {
        **state,
        "status": "CLOSED",
        "winnerOption": winner_option,
        "tallies": tallies,
        "closedAt": SERVER_TIMESTAMP,
    }

    await db.collection(settings.vote_state_collection).document("current").set(window_doc)

    try:
        await set_playback_poll_status(get_redis_client(), vote_id, "CLOSED")
    except Exception:
        logger.exception("Failed to update playback snapshot poll status on close", extra={"voteId": vote_id})
        raise

    logger.info("Closed vote", extra={"voteId": vote_id, "winner": winner_option})
    _publish_vote_event("CLOSE", vote_id, winner_option)
    return window_doc


async def _close_current_vote_if_matches(
    db: AsyncClient,
    expected_vote_id: str | None = None,
    expected_version: int | None = None,
) -> Dict[str, Any]:
    state = await _get_current_state(db)
    if not state:
        return {"action": "noop", "reason": "missing_state"}

    current_vote_id = state.get("voteId")
    current_version = int(state.get("version") or 0)
    current_status = state.get("status")

    if expected_vote_id is not None and current_vote_id != expected_vote_id:
        return {"action": "noop", "reason": "vote_mismatch", "voteId": current_vote_id, "version": current_version}
    if expected_version is not None and current_version != expected_version:
        return {"action": "noop", "reason": "version_mismatch", "voteId": current_vote_id, "version": current_version}
    if current_status != "OPEN":
        return {"action": "noop", "reason": "already_closed", "voteId": current_vote_id, "version": current_version}

    await _close_vote(db, state)
    return {"action": "closed", "voteId": current_vote_id, "version": current_version}


async def _open_next_vote(db: AsyncClient, version: int, duration_ms: int) -> Dict[str, Any]:
    vote_id = str(uuid.uuid4())
    start_at = _utc_now()
    window_options = _get_window_options()
    window_doc = _build_vote(vote_id, start_at, duration_ms, window_options, version)

    await db.collection(settings.vote_state_collection).document("current").set(window_doc)
    logger.info("Opened vote", extra={"voteId": vote_id, "version": version})
    _publish_vote_event("OPEN", vote_id, end_at_ms=_to_epoch_ms(window_doc.get("endAt")))

    return window_doc


# ---------------------------------------------------------------------------
# Tick orchestration helpers
# ---------------------------------------------------------------------------


async def _rotate_song(db: AsyncClient, request_version: int) -> SongRotationResult | None:
    station_ref = db.collection(settings.stations_collection).document("main")
    songs_ref = db.collection(settings.songs_collection)

    @async_transactional
    async def _txn(transaction: AsyncTransaction) -> dict | None:
        now = _utc_now()

        station_snap = await station_ref.get(transaction=transaction)
        if not station_snap.exists:
            raise ValueError("stations/main not found")
        station = station_snap.to_dict() or {}
        current_version = int(station.get("version") or 0)
        if request_version <= current_version:
            return None

        next_data = station.get("next") or {}
        current_vote_id = next_data.get("voteId")
        current_duration = next_data.get("durationMs") or next_data.get("duration")
        if current_vote_id is None or current_duration is None:
            raise ValueError("stations/main.next is missing fields")

        duration_ms = int(current_duration)
        ends_at = now + timedelta(milliseconds=duration_ms)

        candidate_song = await _select_ready_song_candidate(
            transaction,
            songs_ref,
            current_vote_id=str(current_vote_id) if current_vote_id is not None else None,
        )

        if candidate_song is None:
            stubbed_snap = await songs_ref.document("stubbed").get(transaction=transaction)
            if not stubbed_snap.exists:
                raise ValueError("No ready song or stubbed song")
            stubbed_data = stubbed_snap.to_dict() or {}
            stubbed_duration = stubbed_data.get("durationMs")
            if stubbed_duration is None:
                raise ValueError("Stubbed song missing fields")
            candidate_song = {"id": "stubbed", "duration": stubbed_duration, "stubbed": True}

        next_duration_ms = int(candidate_song["duration"])

        transaction.update(station_ref, {
            "voteId": current_vote_id,
            "startAt": now,
            "endAt": ends_at,
            "durationMs": duration_ms,
            "version": request_version,
            "next": {
                "voteId": candidate_song["id"],
                "duration": next_duration_ms,
                "durationMs": next_duration_ms,
            },
        })

        if current_vote_id != "stubbed":
            transaction.update(songs_ref.document(current_vote_id), {"status": "played"})
        if not candidate_song.get("stubbed"):
            transaction.update(songs_ref.document(candidate_song["id"]), {"status": "queued"})

        return {
            "start_at": now,
            "ends_at": ends_at,
            "duration_ms": duration_ms,
            "vote_id": current_vote_id,
            "next_vote_id": candidate_song["id"],
            "next_duration_ms": next_duration_ms,
            "next_stubbed": bool(candidate_song.get("stubbed")),
            "version": request_version,
        }

    transaction = db.transaction()
    try:
        result = await _txn(transaction)
    except ValueError as exc:
        logger.exception("Playback transaction failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception:
        logger.exception("Playback transaction failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to run playback transaction")

    if result is None:
        return None
    return SongRotationResult(**result)


async def _select_ready_song_candidate(
    transaction: AsyncTransaction,
    songs_ref,
    current_vote_id: str | None,
) -> dict | None:
    query = (
        songs_ref
        .where("status", "==", "ready")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(10)
    )
    ready_docs = await query.get(transaction=transaction)
    for doc in ready_docs:
        if current_vote_id and doc.id == current_vote_id:
            continue
        data = doc.to_dict() or {}
        duration_ms = data.get("durationMs")
        if duration_ms is None:
            continue
        return {"id": doc.id, "duration": duration_ms, "stubbed": False}
    return None


async def _rotate_vote(db: AsyncClient, song_duration_ms: int) -> Dict[str, Any]:
    vote_duration_ms = max(0, song_duration_ms - (VOTE_CLOSE_LEAD_SECONDS * 1000))
    state = await _get_current_state(db)
    if state and state.get("status") == "OPEN":
        await _close_vote(db, state)
    version = int(state.get("version") or 0) + 1 if state else 1
    return await _open_next_vote(db, version, vote_duration_ms)


def _build_playback_snapshot(rotation: SongRotationResult, window: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "currentSong": {
            "voteId": rotation.vote_id,
            "startAt": _to_epoch_ms(rotation.start_at),
            "endAt": _to_epoch_ms(rotation.ends_at),
            "durationMs": rotation.duration_ms,
        },
        "nextSong": {
            "voteId": rotation.next_vote_id,
            "durationMs": rotation.next_duration_ms,
        },
        "poll": {
            "voteId": window.get("voteId"),
            "options": window.get("options"),
            "version": window.get("version"),
            "status": "OPEN",
            "endAt": _to_epoch_ms(window.get("endAt")),
        },
    }


def _publish_changeover_events(rotation: SongRotationResult, request_version: int) -> None:
    _publish_playback_event(
        "NEXT-SONG-CHANGED",
        {"voteId": rotation.next_vote_id, "durationMs": rotation.next_duration_ms, "version": request_version},
    )
    _publish_playback_event("CHANGEOVER", {"durationMs": rotation.duration_ms, "version": request_version})


def _schedule_next_tasks(rotation: SongRotationResult, window: Dict[str, Any], request_version: int) -> None:
    if not settings.playback_tick_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PLAYBACK_TICK_URL is required")

    close_vote_id = window.get("voteId")
    close_version = int(window.get("version") or 0)
    try:
        close_delay = max(0.0, (window["endAt"] - _utc_now()).total_seconds())
    except Exception:
        vote_duration_ms = max(0, rotation.duration_ms - (VOTE_CLOSE_LEAD_SECONDS * 1000))
        close_delay = max(0.0, vote_duration_ms / 1000)

    enqueue_json_task_with_delay(
        settings.playback_queue,
        _vote_close_url(),
        {"voteId": close_vote_id, "version": close_version},
        close_delay,
        task_id=_build_vote_close_task_id(str(close_vote_id), close_version),
        ignore_already_exists=True,
    )
    logger.info(
        "Scheduled vote close",
        extra={"voteId": close_vote_id, "version": close_version, "delaySeconds": close_delay},
    )

    next_tick_version = request_version + 1
    delay_seconds = rotation.duration_ms / 1000
    enqueue_json_task_with_delay(
        settings.playback_queue,
        _tick_url(),
        {"version": next_tick_version},
        delay_seconds,
        task_id=_build_tick_task_id(rotation.vote_id, rotation.ends_at, next_tick_version),
        ignore_already_exists=True,
    )
    logger.info(
        "Scheduled next tick",
        extra={"voteId": rotation.vote_id, "delaySeconds": delay_seconds, "version": next_tick_version},
    )


# ---------------------------------------------------------------------------
# Refresh next song helpers
# ---------------------------------------------------------------------------


async def _refresh_next_song(db: AsyncClient, vote_id: str) -> Dict[str, Any]:
    station_ref = db.collection(settings.stations_collection).document("main")
    songs_ref = db.collection(settings.songs_collection)

    @async_transactional
    async def _transaction_fn(transaction: AsyncTransaction) -> Dict[str, Any]:
        station_snap = await station_ref.get(transaction=transaction)
        if not station_snap.exists:
            raise ValueError("stations/main not found")
        station = station_snap.to_dict() or {}
        current_vote_id = station.get("voteId")
        next_data = station.get("next") or {}
        next_vote_id = next_data.get("voteId")
        station_version = int(station.get("version") or 0)

        if next_vote_id != "stubbed":
            existing_duration = next_data.get("durationMs") or next_data.get("duration")
            if existing_duration is None:
                raise ValueError("stations/main.next missing duration")
            return {
                "action": "noop",
                "reason": "next_not_stubbed",
                "voteId": next_vote_id,
                "durationMs": int(existing_duration),
                "version": station_version,
            }

        candidate_song = await _select_ready_song_candidate(
            transaction,
            songs_ref,
            current_vote_id=str(current_vote_id) if current_vote_id is not None else None,
        )
        if candidate_song is None:
            return {
                "action": "noop",
                "reason": "no_ready_song",
                "voteId": next_vote_id,
                "version": station_version,
            }

        duration_ms = int(candidate_song["duration"])
        vote_id = str(candidate_song["id"])
        transaction.update(station_ref, {
            "next": {
                "voteId": vote_id,
                "duration": duration_ms,
                "durationMs": duration_ms,
            },
        })
        transaction.update(songs_ref.document(vote_id), {"status": "queued"})
        return {"action": "updated", "voteId": vote_id, "durationMs": duration_ms, "version": station_version}

    transaction = db.transaction()
    try:
        result = await _transaction_fn(transaction)
    except ValueError as exc:
        logger.exception("Failed to refresh next song")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception:
        logger.exception("Failed to refresh next song", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to refresh next song")

    return result


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@app.post("/vote/close")
async def close_vote(payload: Dict[str, Any]) -> Dict[str, Any]:
    vote_id = payload.get("voteId")
    version_raw = payload.get("version")
    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")
    if version_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version is required")
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be an integer")

    db = get_firestore_client()
    try:
        result = await _close_current_vote_if_matches(db, expected_vote_id=vote_id, expected_version=version)
    except Exception:
        logger.exception("Failed to close vote", extra={"voteId": vote_id, "version": version})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to close vote")

    logger.info("Close vote request handled", extra={"voteId": vote_id, "version": version, "action": result["action"]})
    return {"status": "ok", **result}


@app.post("/next/refresh")
async def refresh_next_song(payload: Dict[str, Any]) -> Dict[str, Any]:
    trigger_vote_id = payload.get("voteId")
    db = get_firestore_client()
    result = await _refresh_next_song(db, str(trigger_vote_id))

    if result is None:
        return {"status": "noop", "reason": "stale_version", "voteId": trigger_vote_id}

    logger.info(
        "Refreshed next song", 
        extra={"voteId": result.get("voteId"), "version": result.get("version")}
    )

    redis_changed: bool | None = None
    if result.get("action") in {"updated", "noop"}:
        try:
            canonical_version = int(result.get("version") or 0)
            redis_changed = await _reconcile_next_song_snapshot(result)
            if redis_changed:
                canonical_vote_id = str(result["voteId"])
                canonical_duration_ms = int(result["durationMs"])
                _publish_playback_event(
                    "NEXT-SONG-CHANGED",
                    {"voteId": canonical_vote_id, "durationMs": canonical_duration_ms, "version": canonical_version},
                )
        except Exception:
            logger.exception("Failed to publish next-song change", extra={"voteId": result.get("voteId")})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to publish next-song change")

    logger.info(
        "Refresh next request handled",
        extra={"result": result, "redisChanged": redis_changed, "triggerVoteId": trigger_vote_id},
    )
    return {"status": "ok", **result}


@app.post("/tick")
async def tick(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_version = _validate_tick_version(payload)
    db = get_firestore_client()

    rotation = await _rotate_song(db, request_version)
    if rotation is None:
        return {"status": "noop", "reason": "stale_version", "requestVersion": request_version}

    logger.info(
        "Selected next song",
        extra={"voteId": rotation.next_vote_id, "stubbed": rotation.next_stubbed, "version": rotation.version},
    )

    try:
        window = await _rotate_vote(db, rotation.duration_ms)
    except Exception:
        logger.exception("Failed to rotate vote")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rotate vote")

    try:
        snapshot = _build_playback_snapshot(rotation, window)
        await _update_redis_on_open(
            window["voteId"], window["startAt"], window["endAt"],
            rotation.duration_ms, window["options"], snapshot,
        )
    except Exception:
        logger.exception("Failed to update Redis playback snapshot", extra={"voteId": window.get("voteId")})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    try:
        _publish_changeover_events(rotation, request_version)
    except Exception:
        logger.exception("Failed to publish playback changeover", extra={"durationMs": rotation.duration_ms})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to publish changeover")
    logger.info("Published playback changeover", extra={"durationMs": rotation.duration_ms})

    _schedule_next_tasks(rotation, window, request_version)
    return {"status": "ok", "version": request_version}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
