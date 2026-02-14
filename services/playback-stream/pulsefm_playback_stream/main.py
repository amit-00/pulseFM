import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from google.cloud.firestore import AsyncClient

from pulsefm_pubsub.client import decode_pubsub_json
from pulsefm_redis.client import get_playback_current_snapshot, get_redis_client, poll_tally_key

from pulsefm_playback_stream.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Playback Stream", version="1.0.0")
_db: AsyncClient | None = None

_dirty_vote_id: str | None = None
_last_invalidated: Dict[str, Any] | None = None


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\n" f"data: {payload}\n\n"


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db


async def _get_vote_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(settings.vote_state_collection).document("current").get()
    return doc.to_dict() if doc.exists else None


async def _get_station_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(settings.stations_collection).document("main").get()
    return doc.to_dict() if doc.exists else None


def _snapshot_cache_ttl_ms(snapshot: Dict[str, Any] | None) -> int:
    if not snapshot:
        return 0
    ends_at = (snapshot.get("currentSong") or {}).get("endAt")
    if isinstance(ends_at, (int, float)):
        return max(0, int(ends_at) - _utc_ms())
    return 0


class _SnapshotCache:
    def __init__(self) -> None:
        self.data: Dict[str, Any] | None = None
        self.expires_at_ms: int = 0

    def valid(self) -> bool:
        return self.data is not None and _utc_ms() < self.expires_at_ms


_snapshot_cache = _SnapshotCache()


def _to_epoch_ms(value: Any) -> int | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    return None


async def _build_state_snapshot(db: AsyncClient) -> Dict[str, Any]:
    station = await _get_station_state(db)
    vote_state = await _get_vote_state(db)
    next_song = (station.get("next") if station else None) or {}
    snapshot = {
        "currentSong": {
            "voteId": station.get("voteId") if station else None,
            "startAt": _to_epoch_ms(station.get("startAt") if station else None),
            "endAt": _to_epoch_ms(station.get("endAt") if station else None),
            "durationMs": station.get("durationMs") if station else None,
        },
        "nextSong": {
            "voteId": next_song.get("voteId"),
            "durationMs": next_song.get("durationMs") or next_song.get("duration"),
        },
        "poll": {
            "voteId": vote_state.get("voteId") if vote_state else None,
            "options": vote_state.get("options") if vote_state else [],
            "version": vote_state.get("version") if vote_state else None,
        },
        "ts": _utc_ms(),
    }
    ttl_ms = _snapshot_cache_ttl_ms(snapshot)
    _snapshot_cache.data = snapshot
    _snapshot_cache.expires_at_ms = _utc_ms() + ttl_ms if ttl_ms > 0 else _utc_ms()
    return snapshot


async def _get_state_snapshot(db: AsyncClient) -> Dict[str, Any]:
    if _snapshot_cache.valid():
        return _snapshot_cache.data or {}
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for snapshot")
        return await _build_state_snapshot(db)

    try:
        snapshot = await get_playback_current_snapshot(redis_client)
    except Exception:
        logger.exception("Redis read failed for snapshot")
        snapshot = None

    if snapshot:
        ttl_ms = _snapshot_cache_ttl_ms(snapshot)
        _snapshot_cache.data = snapshot
        _snapshot_cache.expires_at_ms = _utc_ms() + ttl_ms if ttl_ms > 0 else _utc_ms()
        return snapshot
    return await _build_state_snapshot(db)


async def _get_tallies(redis_client, vote_id: str | None) -> Dict[str, int]:
    if not vote_id:
        return {}
    raw = await redis_client.hgetall(poll_tally_key(vote_id))  # type: ignore[misc]
    tallies: Dict[str, int] = {}
    for option, value in raw.items():
        try:
            tallies[option] = int(value)
        except (TypeError, ValueError):
            tallies[option] = 0
    return tallies


@app.get("/state")
async def state() -> Dict[str, Any]:
    db = get_firestore_client()
    snapshot = await _get_state_snapshot(db)
    vote_id = snapshot.get("poll", {}).get("voteId")
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for state")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    try:
        tallies = await _get_tallies(redis_client, vote_id)
    except Exception:
        logger.exception("Redis read failed for state", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to read tallies")

    snapshot.setdefault("poll", {})["tallies"] = tallies
    return snapshot


def _mark_dirty(vote_id: str) -> None:
    global _dirty_vote_id
    _dirty_vote_id = vote_id


def _consume_dirty(vote_id: str | None) -> bool:
    global _dirty_vote_id
    if vote_id and _dirty_vote_id == vote_id:
        _dirty_vote_id = None
        return True
    return False


def _invalidate_state(vote_id: str | None, version: Any, reason: str) -> None:
    global _last_invalidated
    _last_invalidated = {
        "voteId": vote_id,
        "ts": _utc_ms(),
        "version": version,
        "reason": reason,
    }


@app.post("/events/tally")
async def tally_event(payload: Dict[str, Any]) -> Dict[str, str]:
    message = decode_pubsub_json(payload)
    vote_id = message.get("voteId")
    if not vote_id:
        return {"status": "ignored"}

    try:
        redis_client = get_redis_client()
        snapshot = await get_playback_current_snapshot(redis_client)
    except Exception:
        logger.exception("Redis unavailable for tally event")
        return {"status": "error"}

    current_vote_id = (snapshot or {}).get("poll", {}).get("voteId")
    if current_vote_id == vote_id:
        _mark_dirty(vote_id)
        logger.info("Marked tally dirty", extra={"voteId": vote_id})
    return {"status": "ok"}


@app.post("/events/playback")
async def playback_event(payload: Dict[str, Any]) -> Dict[str, str]:
    message = decode_pubsub_json(payload)
    if message.get("event") != "CHANGEOVER":
        return {"status": "ignored"}

    db = get_firestore_client()
    snapshot = await _get_state_snapshot(db)
    poll = snapshot.get("poll", {})
    _invalidate_state(
        poll.get("voteId"),
        poll.get("version"),
        "song_changed",
    )
    _snapshot_cache.data = None
    logger.info("State invalidated on changeover", extra={"voteId": poll.get("voteId") if poll else None})
    return {"status": "ok"}


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for stream")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    db = get_firestore_client()
    snapshot = await _get_state_snapshot(db)
    vote_id = snapshot.get("poll", {}).get("voteId")
    version = snapshot.get("poll", {}).get("version")
    heartbeat_sec = settings.heartbeat_sec

    yield _format_sse(
        "HELLO",
        {
            "voteId": vote_id,
            "ts": _utc_ms(),
            "version": version,
            "heartbeatSec": heartbeat_sec,
        },
    )

    last_snapshot_at = 0.0
    last_delta_at = 0.0
    last_heartbeat_at = 0.0
    last_invalidated_at = 0.0
    last_tallies: Dict[str, int] = {}

    while True:
        if await request.is_disconnected():
            logger.info("Client disconnected from stream")
            break

        now = asyncio.get_event_loop().time()

        if now - last_snapshot_at >= settings.tally_snapshot_interval_sec:
            tallies = await _get_tallies(redis_client, vote_id)
            last_tallies = tallies
            yield _format_sse(
                "TALLY_SNAPSHOT",
                {"voteId": vote_id, "ts": _utc_ms(), "tallies": tallies},
            )
            last_snapshot_at = now

        if now - last_delta_at >= settings.stream_interval_ms / 1000:
            deltas: Dict[str, int] = {}
            if _consume_dirty(vote_id):
                tallies = await _get_tallies(redis_client, vote_id)
                for option, value in tallies.items():
                    deltas[option] = value - last_tallies.get(option, 0)
                last_tallies = tallies
            else:
                for option in last_tallies.keys():
                    deltas[option] = 0
            yield _format_sse(
                "TALLY_DELTA",
                {"voteId": vote_id, "ts": _utc_ms(), "delta": deltas},
            )
            last_delta_at = now

        if _last_invalidated and _last_invalidated.get("ts", 0) > last_invalidated_at:
            yield _format_sse("STATE_INVALIDATED", _last_invalidated)
            last_invalidated_at = _last_invalidated.get("ts", 0)
            snapshot = await _get_state_snapshot(db)
            vote_id = snapshot.get("poll", {}).get("voteId")
            version = snapshot.get("poll", {}).get("version")

        if now - last_heartbeat_at >= heartbeat_sec:
            yield _format_sse("HEARTBEAT", {"voteId": vote_id, "ts": _utc_ms()})
            last_heartbeat_at = now

        await asyncio.sleep(0.05)


@app.get("/stream")
async def stream_votes(
    request: Request,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
):
    if not x_session_id:
        logger.warning("Missing session id header")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session id")

    logger.info("Stream connected", extra={"sessionId": x_session_id})
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_event_stream(request), headers=headers)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
