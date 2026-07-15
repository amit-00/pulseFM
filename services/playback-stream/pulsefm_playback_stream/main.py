import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generic, TypeVar

from fastapi import FastAPI
from google.cloud.firestore import AsyncClient
from redis.asyncio import Redis

from pulsefm_redis.client import get_playback_current_snapshot, get_redis_client, ping_redis, poll_tally_key

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
# CachedValue[T] – unified cache with staleness and TTL support
# ---------------------------------------------------------------------------


T = TypeVar("T")


class CachedValue(Generic[T]):
    def __init__(self, staleness_ms: int = 0) -> None:
        self.data: T | None = None
        self.fetched_at_ms: int = 0
        self.staleness_ms = staleness_ms

    def is_fresh(self) -> bool:
        if self.fetched_at_ms == 0:
            return False
        return (_utc_ms() - self.fetched_at_ms) < self.staleness_ms

    def set(self, data: T) -> None:
        self.data = data
        self.fetched_at_ms = _utc_ms()

    def set_with_ttl(self, data: T, ttl_ms: int) -> None:
        self.data = data
        self.fetched_at_ms = _utc_ms()
        self.staleness_ms = max(ttl_ms, 0)

    def clear(self) -> None:
        self.data = None
        self.fetched_at_ms = 0


# ---------------------------------------------------------------------------
# StreamState – short-TTL read-through caches over shared stores
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

    # -- snapshot --

    def set_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.snapshot_cache.set_with_ttl(snapshot, _snapshot_ttl_ms(snapshot))

    def clear_snapshot(self) -> None:
        self.snapshot_cache.clear()

    # -- tallies --

    def reset_tallies(self) -> None:
        self.tally_caches.clear()


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


async def _get_tallies(redis_client: Redis | None, vote_id: str | None) -> Dict[str, int]:
    if not vote_id or redis_client is None:
        return {}
    raw = await redis_client.hgetall(poll_tally_key(vote_id))  # type: ignore[misc]
    tallies: Dict[str, int] = {}
    for option, value in raw.items():
        try:
            tallies[option] = int(value)
        except (TypeError, ValueError):
            tallies[option] = 0
    return tallies


async def _count_active_listeners(redis_client: Redis | None) -> int:
    if redis_client is None:
        return 0
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
    state: StreamState, redis_client: Redis | None, vote_id: str | None
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


async def _get_listener_count_cached(state: StreamState, redis_client: Redis | None) -> int | None:
    if redis_client is None:
        return None
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

    redis_available = True
    try:
        redis_client: Redis | None = get_redis_client()
        redis_available = await ping_redis(redis_client)
        if not redis_available:
            redis_client = None
    except Exception:
        logger.warning("Redis unavailable for state; returning degraded response")
        redis_client = None
        redis_available = False

    tallies: Dict[str, int] = {}
    listeners: int | None = None
    if redis_client is not None:
        try:
            tallies = await _get_tallies_cached(s, redis_client, vote_id)
        except Exception:
            logger.warning("Redis read failed for tallies", extra={"voteId": vote_id})
        listeners = await _get_listener_count_cached(s, redis_client)

    poll = _extract_poll(snapshot)
    snapshot["poll"] = poll
    poll["tallies"] = tallies
    poll.setdefault("winnerOption", None)
    snapshot["listeners"] = listeners
    snapshot["redisAvailable"] = redis_available
    return snapshot


@app.get("/health")
async def health() -> Dict[str, Any]:
    redis_ok = False
    try:
        redis_ok = await ping_redis(get_redis_client())
    except Exception:
        pass
    return {"status": "healthy", "redis": redis_ok}
