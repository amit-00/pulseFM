import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from google.cloud import firestore
from google.cloud.firestore import AsyncTransaction, async_transactional

from pulsefm_firestore.client import get_firestore_client
from pulsefm_tasks.client import enqueue_json_task

from pulsefm_playback_orchestrator.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Playback Orchestrator", version="1.0.0")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


def _song_payload(doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "voteId": doc_id,
        "duration": data.get("duration"),
    }


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
        "duration": data.get("duration"),
        "createdAt": data.get("createdAt"),
    }


async def _get_stubbed_song(db) -> Dict[str, Any]:
    doc = await db.collection(settings.songs_collection).document("stubbed").get()
    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No ready song or stubbed song")
    data = doc.to_dict() or {}
    vote_id = data.get("voteId")
    duration = data.get("duration")
    if not vote_id or duration is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stubbed song missing fields")
    return {"id": vote_id, "duration": duration, "stubbed": True}


@app.post("/tick")
async def tick() -> Dict[str, str]:
    db = get_firestore_client()

    ready_song = await _get_ready_song(db)
    if ready_song is None:
        ready_song = await _get_stubbed_song(db)

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
            "startAt": firestore.SERVER_TIMESTAMP,
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

        return {"endsAt": ends_at}

    transaction = db.transaction()
    try:
        result = await _transaction_fn(transaction)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if not settings.vote_orchestrator_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="VOTE_ORCHESTRATOR_URL is required")

    vote_ends_at = result["endsAt"] - timedelta(seconds=20)
    enqueue_json_task(
        settings.vote_orchestrator_queue,
        settings.vote_orchestrator_url,
        {"endsAt": vote_ends_at.isoformat()},
    )

    return {"status": "ok"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
