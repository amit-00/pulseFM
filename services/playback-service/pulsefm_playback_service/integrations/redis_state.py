import logging
from datetime import timedelta
from typing import Any

from pulsefm_redis.client import (
    get_playback_current_snapshot,
    get_poll_tallies,
    get_redis_client,
    init_poll_open_atomic,
    playback_current_key,
    set_playback_current_snapshot,
    set_playback_poll_status,
)

from pulsefm_playback_service.domain.constants import DEFAULT_SNAPSHOT_TTL_SECONDS
from pulsefm_playback_service.utils.time import parse_int, utc_now


class RedisState:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    async def open_poll_snapshot(
        self,
        vote_id: str,
        start_at,
        end_at,
        duration_ms: int,
        options: list[str],
        snapshot: dict[str, Any],
    ) -> None:
        client = get_redis_client()
        current_ttl_seconds = max(1, int(duration_ms / 1000))
        state_ttl_seconds = max(1, int((end_at + timedelta(hours=1) - utc_now()).total_seconds()))
        await init_poll_open_atomic(
            client,
            vote_id,
            snapshot,
            current_ttl_seconds,
            state_ttl_seconds,
            options,
        )

    async def set_poll_status(self, vote_id: str, status: str) -> None:
        await set_playback_poll_status(get_redis_client(), vote_id, status)

    async def get_poll_tallies(self, vote_id: str) -> dict[str, int]:
        return await get_poll_tallies(get_redis_client(), vote_id)

    async def reconcile_next_song_snapshot(self, result: dict[str, Any]) -> bool:
        vote_id = result.get("voteId")
        duration_ms = result.get("durationMs")
        if not isinstance(vote_id, str) or not vote_id:
            return False
        if not isinstance(duration_ms, int) or duration_ms <= 0:
            return False
        return await self._update_playback_next_song_snapshot(vote_id, duration_ms)

    async def _update_playback_next_song_snapshot(self, vote_id: str, duration_ms: int) -> bool:
        client = get_redis_client()
        snapshot = await get_playback_current_snapshot(client)
        if not snapshot:
            raise ValueError("playback snapshot missing")

        next_song = snapshot.get("nextSong")
        if not isinstance(next_song, dict):
            next_song = {}

        desired_duration = int(duration_ms)
        if next_song.get("voteId") == vote_id and parse_int(next_song.get("durationMs")) == desired_duration:
            return False

        next_song["voteId"] = vote_id
        next_song["durationMs"] = desired_duration
        snapshot["nextSong"] = next_song

        ttl = await client.ttl(playback_current_key())  # type: ignore[misc]
        effective_ttl = int(ttl) if ttl and int(ttl) > 0 else DEFAULT_SNAPSHOT_TTL_SECONDS
        await set_playback_current_snapshot(client, snapshot, effective_ttl)
        return True
