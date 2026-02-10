import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from google.cloud.firestore import AsyncClient, AsyncTransaction, async_transactional, SERVER_TIMESTAMP

from pulsefm_tasks.client import enqueue_json_task, enqueue_json_task_with_delay

from pulsefm_playback_orchestrator.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_STARTUP_DELAY_SECONDS = 30


def _build_tick_task_id(vote_id: str | None, ends_at: datetime | None) -> str:
    suffix = vote_id or ""
    timestamp = str(int(ends_at.timestamp())) if ends_at else ""
    return f"playback-{suffix}-{timestamp}"



async def _get_station_state(db) -> Dict[str, Any] | None:
    doc = await db.collection(settings.stations_collection).document("main").get()
    return doc.to_dict() if doc.exists else None


def _remaining_delay_seconds(ends_at: Any) -> int | None:
    if not ends_at:
        return None
    try:
        parsed = _parse_timestamp(ends_at)
    except ValueError:
        return None
    delta = (parsed - _utc_now()).total_seconds()
    return max(0, int(delta))


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
    delay_seconds = _remaining_delay_seconds(ends_at)
    if delay_seconds is None:
        delay_seconds = DEFAULT_STARTUP_DELAY_SECONDS
    parsed_end_at = None
    if ends_at:
        try:
            parsed_end_at = _parse_timestamp(ends_at)
        except ValueError:
            parsed_end_at = None
    task_id = _build_tick_task_id(vote_id, parsed_end_at)
    enqueue_json_task_with_delay(
        settings.playback_queue,
        settings.playback_tick_url.rstrip("/") + "/tick",
        {},
        delay_seconds,
        task_id=task_id,
        ignore_already_exists=True,
    )
    logger.info("Startup tick scheduled", extra={"voteId": vote_id, "delaySeconds": delay_seconds})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_playback_tick_scheduled()
    yield


_db: AsyncClient | None = None


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db


app = FastAPI(title="PulseFM Playback Orchestrator", version="1.0.0", lifespan=lifespan)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


async def _get_ready_song(db) -> Optional[Dict[str, Any]]:
    query = (
        db.collection(settings.songs_collection)
        .where("status", "==", "ready")
        .order_by("createdAt")
        .limit(1)
    )
    docs = await query.get()
    if not docs:
        return None
    doc = docs[0]
    data = doc.to_dict() or {}
    return {
        "id": doc.id,
        "duration": data.get("durationMs"),
        "createdAt": data.get("createdAt"),
    }


async def _get_stubbed_song(db) -> Dict[str, Any]:
    doc = await db.collection(settings.songs_collection).document("stubbed").get()
    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No ready song or stubbed song")
    data = doc.to_dict() or {}
    vote_id = data.get("voteId")
    duration = data.get("durationMs")
    if not vote_id or duration is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stubbed song missing fields")
    return {"id": vote_id, "duration": duration, "stubbed": True}


@app.post("/tick")
async def tick() -> Dict[str, str]:
    db = get_firestore_client()

    try:
        ready_song = await _get_ready_song(db)
    except Exception:
        logger.exception("Failed to get ready song")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get ready song")
    
    if ready_song is None:
        try:
            ready_song = await _get_stubbed_song(db)
        except Exception:
            logger.exception("Failed to get stubbed song")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get stubbed song")
            
    logger.info("Selected song", extra={"voteId": ready_song.get("id"), "stubbed": ready_song.get("stubbed", False)})

    station_ref = db.collection(settings.stations_collection).document("main")
    songs_ref = db.collection(settings.songs_collection)

    now = _utc_now()

    @async_transactional
    async def _transaction_fn(transaction: AsyncTransaction) -> Dict[str, Any]:
        station_snap = await station_ref.get(transaction=transaction)
        if not station_snap.exists:
            raise ValueError("stations/main not found")
        station = station_snap.to_dict() or {}

        next_data = station.get("next") or {}
        current_vote_id = next_data.get("voteId")
        current_duration = next_data.get("duration")
        if current_vote_id is None or current_duration is None:
            raise ValueError("stations/main.next is missing fields")

        duration_ms = int(current_duration)
        ends_at = now + timedelta(milliseconds=duration_ms)

        transaction.update(station_ref, {
            "voteId": current_vote_id,
            "startAt": SERVER_TIMESTAMP,
            "endAt": ends_at,
            "durationMs": duration_ms,
            "next": {
                "voteId": ready_song["id"],
                "duration": ready_song["duration"],
            },
        })

        if not ready_song.get("stubbed"):
            song_ref = songs_ref.document(ready_song["id"])
            transaction.update(song_ref, {"status": "played"})

        return {"endsAt": ends_at, "durationMs": duration_ms, "voteId": current_vote_id}

    transaction = db.transaction()
    try:
        result = await _transaction_fn(transaction)
    except ValueError as exc:
        logger.exception("Playback transaction failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if not settings.vote_orchestrator_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="VOTE_ORCHESTRATOR_URL is required")

    vote_orchestrator_url = settings.vote_orchestrator_url.rstrip("/") + "/open"
    vote_ends_at = result["endsAt"] - timedelta(seconds=20)
    enqueue_json_task(
        settings.vote_orchestrator_queue,
        vote_orchestrator_url,
        {"endsAt": vote_ends_at.isoformat()},
    )
    logger.info("Enqueued vote open", extra={"voteEndsAt": vote_ends_at.isoformat()})

    if not settings.playback_tick_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PLAYBACK_TICK_URL is required")

    playback_tick_url = settings.playback_tick_url.rstrip("/") + "/tick"
    duration_ms = result.get("durationMs")
    try:
        delay_seconds = int(duration_ms) / 1000 if duration_ms else 30
    except (TypeError, ValueError):
        delay_seconds = 30

    task_id = _build_tick_task_id(result.get("voteId"), result.get("endsAt"))
    enqueue_json_task_with_delay(
        settings.playback_queue,
        playback_tick_url,
        {},
        int(delay_seconds),
        task_id=task_id,
        ignore_already_exists=True,
    )
    logger.info("Scheduled next tick", extra={"voteId": result.get("voteId"), "delaySeconds": int(delay_seconds)})

    return {"status": "ok"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
