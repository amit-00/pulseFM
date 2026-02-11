import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import uuid

import modal
from fastapi import FastAPI, HTTPException, status
from google.cloud.firestore import AsyncClient, SERVER_TIMESTAMP

from pulsefm_descriptors.data import DESCRIPTORS, get_descriptor_keys
from pulsefm_tasks.client import enqueue_json_task_with_delay
from pulsefm_redis.client import (
    close_poll_state,
    get_redis_client,
    set_current_poll,
    set_poll_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote Orchestrator", version="1.0.0")
_db: AsyncClient | None = None


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db

VOTE_STATE_COLLECTION = os.getenv("VOTE_STATE_COLLECTION", "voteState")
VOTE_WINDOWS_COLLECTION = os.getenv("VOTE_WINDOWS_COLLECTION", "voteWindows")
HEARTBEAT_COLLECTION = os.getenv("HEARTBEAT_COLLECTION", "heartbeat")
VOTE_ORCHESTRATOR_QUEUE = os.getenv("VOTE_ORCHESTRATOR_QUEUE", "vote-orchestrator-queue")
VOTE_ORCHESTRATOR_URL = os.getenv("VOTE_ORCHESTRATOR_URL", "")
WINDOW_SECONDS = int(os.getenv("WINDOW_SECONDS", "300"))
OPTIONS_PER_WINDOW = int(os.getenv("OPTIONS_PER_WINDOW", "4"))
VOTE_OPTIONS = [opt.strip() for opt in os.getenv("VOTE_OPTIONS", "").split(",") if opt.strip()]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_current_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(VOTE_STATE_COLLECTION).document("current").get()
    return doc.to_dict() if doc.exists else None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


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
    if VOTE_OPTIONS:
        return VOTE_OPTIONS
    options = get_descriptor_keys()
    if len(options) < OPTIONS_PER_WINDOW:
        raise ValueError("Not enough descriptor options to sample window choices")
    return random.sample(options, OPTIONS_PER_WINDOW)


async def _get_active_listeners(db: AsyncClient) -> int:
    """Read the heartbeat/main doc and return the active_listeners count."""
    doc = await db.collection(HEARTBEAT_COLLECTION).document("main").get()
    if not doc.exists:
        return 0
    data = doc.to_dict()
    return data.get("active_listeners", 0) if data else 0


async def _dispatch_modal_worker(vote_id: str, winner_option: str) -> None:
    """Dispatch the Modal worker to generate music for the winning option."""
    descriptor = DESCRIPTORS.get(winner_option)
    if not descriptor:
        logger.warning("No descriptor found for winner option: %s", winner_option)
        return

    genre = descriptor["genre"]
    mood = descriptor["mood"]
    energy = descriptor["energy"]

    logger.info(
        "Dispatching Modal worker: vote_id=%s, winner=%s, genre=%s, mood=%s, energy=%s",
        vote_id, winner_option, genre, mood, energy
    )

    MusicGenerator = modal.Cls.from_name("pulsefm-worker", "MusicGenerator")
    generator = MusicGenerator()
    await generator.generate.spawn.aio(
        genre=genre,
        mood=mood,
        energy=energy,
        vote_id=vote_id
    )


def _pick_winner(tallies: Dict[str, Any]) -> str | None:
    if not tallies:
        return None
    max_votes = max(tallies.values())
    tied = [option for option, count in tallies.items() if count == max_votes]
    return random.choice(tied) if tied else None


async def _close_vote(db: AsyncClient, state: Dict[str, Any]) -> Dict[str, Any]:
    vote_id = state.get("voteId")
    tallies = state.get("tallies") or {}
    if not vote_id:
        raise ValueError("voteId missing from voteState/current")
    winner_option = _pick_winner(tallies)

    closed_at = SERVER_TIMESTAMP

    window_doc = {
        **state,
        "status": "CLOSED",
        "winnerOption": winner_option,
        "tallies": tallies,
        "closedAt": closed_at,
    }

    await db.collection(VOTE_WINDOWS_COLLECTION).document(vote_id).set(window_doc)
    await db.collection(VOTE_STATE_COLLECTION).document("current").set(window_doc)
    logger.info("Closed vote", extra={"voteId": vote_id, "winner": winner_option})

    # Check active listeners and dispatch Modal worker if needed
    if winner_option and vote_id:
        active_listeners = await _get_active_listeners(db)
        if active_listeners >= 1:
            logger.info("Active listeners: %d, dispatching Modal worker", active_listeners)
            await _dispatch_modal_worker(vote_id, winner_option)
        else:
            logger.info("No active listeners, skipping Modal worker dispatch")

    return window_doc


def _update_redis_on_open(vote_id: str, start_at: datetime, end_at: datetime, duration_ms: int) -> None:
    client = get_redis_client()

    current_ttl_seconds = max(1, int((duration_ms * 2) / 1000))
    state_ttl_seconds = max(1, int((end_at + timedelta(days=7) - _utc_now()).total_seconds()))

    set_current_poll(client, vote_id, current_ttl_seconds)
    set_poll_state(
        client,
        vote_id,
        "open",
        int(start_at.timestamp() * 1000),
        int(end_at.timestamp() * 1000),
        state_ttl_seconds,
    )


def _update_redis_on_close(vote_id: str) -> None:
    client = get_redis_client()
    close_poll_state(client, vote_id)


def _schedule_close(vote_id: str, ends_at: datetime) -> None:
    if not VOTE_ORCHESTRATOR_URL:
        raise ValueError("VOTE_ORCHESTRATOR_URL is required")
    delay_seconds = max(0, int((ends_at - _utc_now()).total_seconds()))
    close_url = VOTE_ORCHESTRATOR_URL.rstrip("/") + "/close"
    logger.info("Scheduling close", extra={"voteId": vote_id, "delaySeconds": delay_seconds})
    enqueue_json_task_with_delay(
        VOTE_ORCHESTRATOR_QUEUE,
        close_url,
        {"voteId": vote_id},
        delay_seconds,
        task_id=f"close-{vote_id}",
        ignore_already_exists=True,
    )


async def _open_next_vote(db: AsyncClient, version: int, duration_ms: int) -> Dict[str, Any]:
    vote_id = str(uuid.uuid4())
    start_at = _utc_now()
    window_options = _get_window_options()

    window_doc = _build_vote(vote_id, start_at, duration_ms, window_options, version)
    await db.collection(VOTE_STATE_COLLECTION).document("current").set(window_doc)
    await db.collection(VOTE_WINDOWS_COLLECTION).document(vote_id).set(window_doc)
    logger.info("Opened vote", extra={"voteId": vote_id, "version": version})

    return window_doc


@app.post("/close")
async def close_vote(payload: Dict[str, Any]) -> Dict[str, Any]:
    vote_id = payload.get("voteId")
    if not vote_id:
        logger.warning("Missing voteId on close")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")
    db = get_firestore_client()
    state = await _get_current_state(db)
    if not state:
        logger.info("Close noop; no state")
        return {"status": "noop"}
    if state.get("voteId") != vote_id:
        logger.info("Close voteId mismatch", extra={"requested": vote_id, "current": state.get("voteId")})
        return {"status": "vote_id_mismatch", "voteId": state.get("voteId")}
    if state.get("status") != "OPEN":
        logger.info("Already closed", extra={"voteId": state.get("voteId")})
        return {"status": "already_closed", "voteId": state.get("voteId")}
    try:
        window = await _close_vote(db, state)
        _update_redis_on_close(window["voteId"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to update Redis on close", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return {"status": "closed", "voteId": window.get("voteId")}


@app.post("/open")
async def open_vote(payload: Dict[str, Any]) -> Dict[str, Any]:
    duration_ms_raw = payload.get("durationMs")
    if duration_ms_raw is None:
        logger.warning("Missing durationMs on open")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="durationMs is required")
    try:
        duration_ms = int(duration_ms_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid durationMs")
    if duration_ms < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="durationMs must not be negative")

    db = get_firestore_client()
    state = await _get_current_state(db)

    if not state:
        window = await _open_next_vote(db, 1, duration_ms)
        try:
            _update_redis_on_open(window["voteId"], window["startAt"], window["endAt"], duration_ms)
        except Exception as exc:
            logger.exception("Failed to update Redis on open", extra={"voteId": window["voteId"]})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        _schedule_close(window["voteId"], window["endAt"])
        return {"status": "opened", "voteId": window["voteId"]}

    poll_status = state.get("status")

    if poll_status == "OPEN":
        try:
            await _close_vote(db, state)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        window = await _open_next_vote(db, int(state.get("version", 0)) + 1, duration_ms)
        try:
            _update_redis_on_open(window["voteId"], window["startAt"], window["endAt"], duration_ms)
        except Exception as exc:
            logger.exception("Failed to update Redis on open", extra={"voteId": window["voteId"]})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
        _schedule_close(window["voteId"], window["endAt"])
        return {"status": "rotated", "voteId": window["voteId"]}

    window = await _open_next_vote(db, int(state.get("version", 0)) + 1, duration_ms)
    try:
        _update_redis_on_open(window["voteId"], window["startAt"], window["endAt"], duration_ms)
    except Exception as exc:
        logger.exception("Failed to update Redis on open", extra={"voteId": window["voteId"]})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    _schedule_close(window["voteId"], window["endAt"])
    return {"status": "opened", "voteId": window["voteId"]}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
