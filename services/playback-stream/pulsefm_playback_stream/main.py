import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Generic, TypeVar

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from google.cloud.firestore import AsyncClient
from redis.asyncio import Redis

from pulsefm_pubsub.client import decode_pubsub_json
from pulsefm_redis.client import get_playback_current_snapshot, get_redis_client, poll_tally_key

from pulsefm_playback_stream.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TALLY_CACHE_STALENESS_MS = 500
LISTENER_CACHE_STALENESS_MS = 1000


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _monotonic_now() -> float:
    return asyncio.get_event_loop().time()


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_epoch_ms(value: Any) -> int | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _extract_poll(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    poll = snapshot.get("poll")
    return poll if isinstance(poll, dict) else {}


# ---------------------------------------------------------------------------
# CachedValue[T] – unified cache with staleness, TTL, and dirty-flag support
# ---------------------------------------------------------------------------


T = TypeVar("T")


class CachedValue(Generic[T]):
    def __init__(self, staleness_ms: int = 0) -> None:
        self.data: T | None = None
        self.fetched_at_ms: int = 0
        self.staleness_ms = staleness_ms
        self.dirty: bool = False

    def is_fresh(self) -> bool:
        if self.dirty or self.fetched_at_ms == 0:
            return False
        return (_utc_ms() - self.fetched_at_ms) < self.staleness_ms

    def set(self, data: T) -> None:
        self.data = data
        self.fetched_at_ms = _utc_ms()
        self.dirty = False

    def set_with_ttl(self, data: T, ttl_ms: int) -> None:
        self.data = data
        self.fetched_at_ms = _utc_ms()
        self.staleness_ms = max(ttl_ms, 0)
        self.dirty = False

    def clear(self) -> None:
        self.data = None
        self.fetched_at_ms = 0
        self.dirty = False

    def mark_dirty(self) -> None:
        self.dirty = True


# ---------------------------------------------------------------------------
# StreamState – single home for all mutable process state
# ---------------------------------------------------------------------------


def _snapshot_ttl_ms(snapshot: Dict[str, Any]) -> int:
    ends_at = (snapshot.get("currentSong") or {}).get("endAt")
    if isinstance(ends_at, (int, float)):
        return max(0, int(ends_at) - _utc_ms())
    return 0


class StreamState:
    def __init__(self) -> None:
        self.snapshot_cache: CachedValue[Dict[str, Any]] = CachedValue()
        self.tally_caches: Dict[str, CachedValue[Dict[str, int]]] = {}
        self.tally_lock = asyncio.Lock()
        self.listener_cache: CachedValue[int] = CachedValue(staleness_ms=LISTENER_CACHE_STALENESS_MS)
        self.listener_lock = asyncio.Lock()
        self.last_invalidated: Dict[str, Any] | None = None
        self.last_vote_closed: Dict[str, Any] | None = None
        self.last_next_song_changed: Dict[str, Any] | None = None
        self.last_playback_version: int = 0

    # -- snapshot --

    def set_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_cache.set_with_ttl(snapshot, _snapshot_ttl_ms(snapshot))

    def clear_snapshot(self) -> None:
        self.snapshot_cache.clear()

    # -- tallies --

    def is_tally_dirty(self, vote_id: str | None) -> bool:
        if not vote_id:
            return False
        cache = self.tally_caches.get(vote_id)
        return cache is not None and cache.dirty

    def mark_tally_dirty(self, vote_id: str | None) -> None:
        if not vote_id:
            return
        cache = self.tally_caches.get(vote_id)
        if cache is None:
            cache = CachedValue[Dict[str, int]](staleness_ms=TALLY_CACHE_STALENESS_MS)
            cache.dirty = True
            self.tally_caches[vote_id] = cache
        else:
            cache.mark_dirty()

    def reset_tallies(self) -> None:
        self.tally_caches.clear()

    # -- event recording --

    def invalidate(self, vote_id: str | None, version: Any) -> None:
        self.last_invalidated = {"voteId": vote_id, "ts": _utc_ms(), "version": version}

    def record_vote_closed(self, vote_id: str | None, winner_option: str | None) -> None:
        self.last_vote_closed = {"voteId": vote_id, "winnerOption": winner_option, "ts": _utc_ms()}

    def record_next_song_changed(
        self, vote_id: str | None, duration_ms: Any, version: int | None = None
    ) -> None:
        self.last_next_song_changed = {
            "voteId": vote_id,
            "durationMs": _parse_int(duration_ms),
            "version": version,
            "ts": _utc_ms(),
        }

    # -- queries --

    def is_stale_event(self, event_version: int | None) -> bool:
        return event_version is not None and event_version < self.last_playback_version

    def winner_for_vote(self, vote_id: str | None) -> str | None:
        if not vote_id or not self.last_vote_closed:
            return None
        if self.last_vote_closed.get("voteId") != vote_id:
            return None
        winner = self.last_vote_closed.get("winnerOption")
        return winner if isinstance(winner, str) and winner else None

    def stream_event_markers(self, connected_at_ms: int) -> Dict[str, int]:
        return {
            "last_invalidated_at": max(connected_at_ms, int((self.last_invalidated or {}).get("ts", 0))),
            "last_vote_closed_at": max(connected_at_ms, int((self.last_vote_closed or {}).get("ts", 0))),
            "last_next_song_changed_at": max(
                connected_at_ms, int((self.last_next_song_changed or {}).get("ts", 0))
            ),
        }


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

_db: AsyncClient | None = None


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


# ---------------------------------------------------------------------------
# Snapshot building / fetching
# ---------------------------------------------------------------------------


async def _build_state_snapshot(state: StreamState, db: AsyncClient) -> Dict[str, Any]:
    station = (await _get_station_state(db)) or {}
    vote_state = (await _get_vote_state(db)) or {}
    next_song = station.get("next") or {}
    snapshot = {
        "currentSong": {
            "voteId": station.get("voteId"),
            "startAt": _to_epoch_ms(station.get("startAt")),
            "endAt": _to_epoch_ms(station.get("endAt")),
            "durationMs": station.get("durationMs"),
        },
        "nextSong": {
            "voteId": next_song.get("voteId"),
            "durationMs": next_song.get("durationMs") or next_song.get("duration"),
        },
        "poll": {
            "voteId": vote_state.get("voteId"),
            "options": vote_state.get("options") or [],
            "version": vote_state.get("version"),
            "status": vote_state.get("status"),
            "endAt": _to_epoch_ms(vote_state.get("endAt")),
            "winnerOption": vote_state.get("winnerOption"),
        },
        "ts": _utc_ms(),
    }
    state.set_snapshot(snapshot)
    return snapshot


async def _get_state_snapshot(state: StreamState, db: AsyncClient) -> Dict[str, Any]:
    if state.snapshot_cache.is_fresh() and state.snapshot_cache.data is not None:
        return state.snapshot_cache.data

    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for snapshot")
        return await _build_state_snapshot(state, db)

    try:
        snapshot = await get_playback_current_snapshot(redis_client)
    except Exception:
        logger.exception("Redis read failed for snapshot")
        snapshot = None

    if snapshot:
        state.set_snapshot(snapshot)
        return snapshot
    return await _build_state_snapshot(state, db)


# ---------------------------------------------------------------------------
# Redis data fetching
# ---------------------------------------------------------------------------


async def _get_tallies(redis_client: Redis, vote_id: str | None) -> Dict[str, int]:
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


async def _count_active_listeners(redis_client: Redis) -> int:
    active = await redis_client.get("pulsefm:heartbeat:active")  # type: ignore[misc]
    if not active:
        return 0
    count = 0
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(  # type: ignore[misc]
            cursor=cursor,
            match="pulsefm:heartbeat:session:*",
            count=1000,
        )
        count += len(keys or [])
        if int(cursor) == 0:
            break
    return count


# ---------------------------------------------------------------------------
# Cached data fetching
# ---------------------------------------------------------------------------


async def _get_tallies_cached(
    state: StreamState, redis_client: Redis, vote_id: str | None
) -> Dict[str, int]:
    if not vote_id:
        return {}

    cache = state.tally_caches.get(vote_id)
    if cache and cache.is_fresh():
        return cache.data or {}

    async with state.tally_lock:
        cache = state.tally_caches.get(vote_id)
        if cache and cache.is_fresh():
            return cache.data or {}
        tallies = await _get_tallies(redis_client, vote_id)
        new_cache = CachedValue[Dict[str, int]](staleness_ms=TALLY_CACHE_STALENESS_MS)
        new_cache.set(tallies)
        state.tally_caches[vote_id] = new_cache
        return tallies


async def _get_listener_count_cached(state: StreamState, redis_client: Redis) -> int | None:
    if state.listener_cache.is_fresh():
        return state.listener_cache.data

    async with state.listener_lock:
        if state.listener_cache.is_fresh():
            return state.listener_cache.data
        try:
            count = await _count_active_listeners(redis_client)
            state.listener_cache.set(count)
        except Exception:
            state.listener_cache.data = None
            state.listener_cache.fetched_at_ms = _utc_ms()
        return state.listener_cache.data


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _next_song_conflicts(snapshot: Dict[str, Any] | None, vote_id: Any, duration_ms: Any) -> bool:
    if not snapshot:
        return False
    cached_next = snapshot.get("nextSong")
    if not isinstance(cached_next, dict):
        return True
    return (
        cached_next.get("voteId") != vote_id
        or _parse_int(cached_next.get("durationMs")) != _parse_int(duration_ms)
    )


def _build_tally_snapshot_payload(
    state: StreamState, vote_id: str | None, tallies: Dict[str, int], snapshot: Dict[str, Any]
) -> Dict[str, Any]:
    poll = _extract_poll(snapshot)
    return {
        "voteId": vote_id,
        "ts": _utc_ms(),
        "tallies": tallies,
        "status": poll.get("status"),
        "winnerOption": poll.get("winnerOption") or state.winner_for_vote(vote_id),
    }


def _build_hello_payload(vote_id: str | None, version: Any, heartbeat_sec: int) -> Dict[str, Any]:
    return {
        "voteId": vote_id,
        "ts": _utc_ms(),
        "version": version,
        "heartbeatSec": heartbeat_sec,
    }


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------


async def _handle_next_song_changed_event(
    state: StreamState, message: Dict[str, Any], event_version: int | None
) -> Dict[str, str]:
    if event_version is None:
        logger.warning("Missing version on next-song event")
        return {"status": "ignored"}

    if state.is_stale_event(event_version):
        logger.info(
            "Dropped stale next-song event",
            extra={"version": event_version, "lastVersion": state.last_playback_version},
        )
        return {"status": "ignored"}

    if event_version == state.last_playback_version:
        if _next_song_conflicts(state.snapshot_cache.data, message.get("voteId"), message.get("durationMs")):
            state.clear_snapshot()
            db = get_firestore_client()
            refreshed = await _get_state_snapshot(state, db)
            refreshed_next = refreshed.get("nextSong") or {}
            state.record_next_song_changed(
                refreshed_next.get("voteId"),
                refreshed_next.get("durationMs"),
                event_version,
            )
            logger.warning("Next-song conflict detected; forced state refresh", extra={"version": event_version})
            return {"status": "ok"}
        return {"status": "ignored"}

    state.last_playback_version = event_version
    state.record_next_song_changed(message.get("voteId"), message.get("durationMs"), event_version)
    state.clear_snapshot()
    logger.info(
        "Recorded next-song change event",
        extra={"voteId": message.get("voteId"), "version": event_version},
    )
    return {"status": "ok"}


async def _handle_changeover_event(state: StreamState, event_version: int | None) -> Dict[str, str]:
    if state.is_stale_event(event_version):
        logger.info(
            "Dropped stale changeover event",
            extra={"version": event_version, "lastVersion": state.last_playback_version},
        )
        return {"status": "ignored"}

    if event_version is not None:
        state.last_playback_version = event_version

    db = get_firestore_client()
    state.clear_snapshot()
    snapshot = await _get_state_snapshot(state, db)
    poll = _extract_poll(snapshot)

    state.reset_tallies()
    state.listener_cache.clear()
    state.invalidate(
        poll.get("voteId"),
        event_version if event_version is not None else poll.get("version"),
    )

    logger.info(
        "State invalidated on changeover",
        extra={"voteId": poll.get("voteId"), "version": event_version},
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


@dataclass
class _LoopState:
    vote_id: str | None
    last_tallies: Dict[str, int]
    last_snapshot_at: float
    last_delta_at: float
    last_heartbeat_at: float
    markers: Dict[str, int]


async def _check_marker_events(
    state: StreamState, loop: _LoopState, db: AsyncClient
) -> AsyncGenerator[str, None]:
    if (
        state.last_invalidated
        and state.last_invalidated.get("ts", 0) > loop.markers["last_invalidated_at"]
    ):
        loop.markers["last_invalidated_at"] = state.last_invalidated.get("ts", 0)
        snapshot = await _get_state_snapshot(state, db)
        new_vote_id = _extract_poll(snapshot).get("voteId")
        yield _format_sse("SONG_CHANGED", state.last_invalidated)
        if new_vote_id is not None:
            loop.vote_id = new_vote_id
            loop.last_tallies = {}
            loop.last_snapshot_at = 0.0
            loop.last_delta_at = 0.0

    if (
        state.last_vote_closed
        and state.last_vote_closed.get("ts", 0) > loop.markers["last_vote_closed_at"]
    ):
        loop.markers["last_vote_closed_at"] = state.last_vote_closed.get("ts", 0)
        yield _format_sse("VOTE_CLOSED", state.last_vote_closed)

    if (
        state.last_next_song_changed
        and state.last_next_song_changed.get("ts", 0) > loop.markers["last_next_song_changed_at"]
    ):
        loop.markers["last_next_song_changed_at"] = state.last_next_song_changed.get("ts", 0)
        yield _format_sse("NEXT-SONG-CHANGED", state.last_next_song_changed)


async def _check_timed_events(
    state: StreamState, loop: _LoopState, db: AsyncClient, redis_client: Redis, now: float
) -> AsyncGenerator[str, None]:
    if now - loop.last_snapshot_at >= settings.tally_snapshot_interval_sec:
        tallies = await _get_tallies_cached(state, redis_client, loop.vote_id)
        snapshot = await _get_state_snapshot(state, db)
        payload = _build_tally_snapshot_payload(state, loop.vote_id, tallies, snapshot)
        yield _format_sse("TALLY_SNAPSHOT", payload)
        loop.last_tallies = tallies
        loop.last_snapshot_at = _monotonic_now()

    if now - loop.last_delta_at >= settings.stream_interval_ms / 1000:
        tallies = await _get_tallies_cached(state, redis_client, loop.vote_id)
        listener_count = await _get_listener_count_cached(state, redis_client)
        deltas: Dict[str, int] = {}
        for option, value in tallies.items():
            deltas[option] = value - loop.last_tallies.get(option, 0)
        for option in loop.last_tallies:
            if option not in deltas:
                deltas[option] = 0
        payload = {"voteId": loop.vote_id, "ts": _utc_ms(), "delta": deltas, "listeners": listener_count}
        yield _format_sse("TALLY_DELTA", payload)
        loop.last_tallies = tallies
        loop.last_delta_at = _monotonic_now()

    if now - loop.last_heartbeat_at >= settings.heartbeat_sec:
        yield _format_sse("HEARTBEAT", {"voteId": loop.vote_id, "ts": _utc_ms()})
        loop.last_heartbeat_at = _monotonic_now()


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    state: StreamState = request.app.state.stream
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for stream")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    db = get_firestore_client()
    snapshot = await _get_state_snapshot(state, db)
    poll = _extract_poll(snapshot)
    vote_id = poll.get("voteId")

    yield _format_sse("HELLO", _build_hello_payload(vote_id, poll.get("version"), settings.heartbeat_sec))

    state.mark_tally_dirty(vote_id)
    initial_tallies = await _get_tallies_cached(state, redis_client, vote_id)
    yield _format_sse("TALLY_SNAPSHOT", _build_tally_snapshot_payload(state, vote_id, initial_tallies, snapshot))

    loop = _LoopState(
        vote_id=vote_id,
        last_tallies=initial_tallies,
        last_snapshot_at=_monotonic_now(),
        last_delta_at=0.0,
        last_heartbeat_at=0.0,
        markers=state.stream_event_markers(_utc_ms()),
    )

    while True:
        if await request.is_disconnected():
            logger.info("Client disconnected from stream")
            break
        now = _monotonic_now()
        async for event in _check_marker_events(state, loop, db):
            yield event
        async for event in _check_timed_events(state, loop, db, redis_client, now):
            yield event
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(a: FastAPI):
    a.state.stream = StreamState()
    yield


app = FastAPI(title="PulseFM Playback Stream", version="1.0.0", lifespan=_lifespan)


@app.get("/state")
async def get_state() -> Dict[str, Any]:
    s: StreamState = app.state.stream
    db = get_firestore_client()
    snapshot = await _get_state_snapshot(s, db)
    vote_id = snapshot.get("poll", {}).get("voteId")
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for state")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    try:
        tallies = await _get_tallies_cached(s, redis_client, vote_id)
    except Exception:
        logger.exception("Redis read failed for state", extra={"voteId": vote_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to read tallies")
    listeners = await _get_listener_count_cached(s, redis_client)

    poll = _extract_poll(snapshot)
    snapshot["poll"] = poll
    poll["tallies"] = tallies
    if poll.get("winnerOption") is None:
        poll["winnerOption"] = s.winner_for_vote(vote_id)
    snapshot["listeners"] = listeners
    return snapshot


@app.post("/events/tally")
async def tally_event(payload: Dict[str, Any]) -> Dict[str, str]:
    s: StreamState = app.state.stream
    message = decode_pubsub_json(payload)
    vote_id = message.get("voteId")
    if not vote_id:
        return {"status": "ignored"}

    if s.is_tally_dirty(vote_id):
        logger.info("Tally cache is dirty; ignoring tally event", extra={"voteId": vote_id})
        return {"status": "ignored"}

    try:
        redis_client = get_redis_client()
        snapshot = await get_playback_current_snapshot(redis_client)
    except Exception:
        logger.exception("Redis unavailable for tally event")
        return {"status": "error"}

    current_vote_id = (snapshot or {}).get("poll", {}).get("voteId")
    if current_vote_id == vote_id:
        s.mark_tally_dirty(vote_id)
        logger.info("Marked tally dirty", extra={"voteId": vote_id})
    return {"status": "ok"}


@app.post("/events/playback")
async def playback_event(payload: Dict[str, Any]) -> Dict[str, str]:
    s: StreamState = app.state.stream
    message = decode_pubsub_json(payload)
    event_type = message.get("event")
    event_version = _parse_int(message.get("version"))

    if event_type == "NEXT-SONG-CHANGED":
        return await _handle_next_song_changed_event(s, message, event_version)

    if event_type != "CHANGEOVER":
        return {"status": "ignored"}

    return await _handle_changeover_event(s, event_version)


@app.post("/events/vote")
async def vote_event(payload: Dict[str, Any]) -> Dict[str, str]:
    s: StreamState = app.state.stream
    message = decode_pubsub_json(payload)
    if message.get("event") != "CLOSE":
        return {"status": "ignored"}

    vote_id = message.get("voteId")
    winner_option = message.get("winnerOption")
    s.record_vote_closed(vote_id, winner_option)
    logger.info("Recorded vote close event", extra={"voteId": vote_id, "winnerOption": winner_option})
    return {"status": "ok"}


@app.get("/stream")
async def stream_votes(request: Request):
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
