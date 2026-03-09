from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from config import RuntimeConfig, STUBBED_SONG_ID
from helpers import utc_ms
from song_repository import SongRepository

STATE_KEY = "station-state-v1"


class PlaybackOrchestrator:
    def __init__(
        self,
        ctx,
        env,
        songs: SongRepository | None = None,
        config: RuntimeConfig | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._ctx = ctx
        self._env = env
        self._config = config or RuntimeConfig.from_env(
            {
                "VOTE_OPTIONS": getattr(env, "VOTE_OPTIONS", ""),
                "OPTIONS_PER_WINDOW": getattr(env, "OPTIONS_PER_WINDOW", "4"),
                "STUBBED_DURATION_MS": getattr(env, "STUBBED_DURATION_MS", "300000"),
                "VOTE_CLOSE_LEAD_SECONDS": getattr(env, "VOTE_CLOSE_LEAD_SECONDS", "60"),
            }
        )
        self._songs = songs or SongRepository(env.PLAYBACK_DB)
        self._clock = clock or utc_ms
        self._state_cache: dict[str, Any] | None = None

    async def state_snapshot(self) -> dict[str, Any]:
        state = await self._get_state()
        return self._snapshot_response(state)

    async def start(self) -> dict[str, Any]:
        state = await self._get_state()
        now = self._clock()

        current_song = state.get("current_song")
        if current_song is None:
            await self._initialize_loop(state, now)
            await self._persist_state(state)
            return self._snapshot_response(state)

        changed = await self._apply_due_transitions(state, now)
        if changed:
            await self._persist_state(state)
        else:
            await self._sync_alarm(state)

        return self._snapshot_response(state)

    async def handle_alarm(self) -> None:
        state = await self._get_state()
        changed = await self._apply_due_transitions(state, self._clock())
        if changed:
            await self._persist_state(state)
        else:
            await self._sync_alarm(state)

    async def _initialize_loop(self, state: dict[str, Any], now: int) -> None:
        current_song = await self._select_song_for_current(exclude_song_ids=set())
        next_song = await self._select_song_for_next(exclude_song_ids={current_song["songId"]})

        state["current_song"] = self._song_window(current_song, now)
        state["next_song"] = next_song
        state["poll"] = self._open_poll(state["current_song"], now)
        state["updated_at"] = now

    async def _apply_due_transitions(self, state: dict[str, Any], now: int) -> bool:
        changed = False

        poll = state.get("poll")
        if poll and poll.get("is_open") and int(poll.get("end_at", 0)) <= now:
            poll["is_open"] = False
            state["updated_at"] = now
            changed = True

        current_song = state.get("current_song")
        if current_song and int(current_song.get("end_at", 0)) <= now:
            await self._advance_song(state, now)
            changed = True

        return changed

    async def _advance_song(self, state: dict[str, Any], now: int) -> None:
        promoted_song = state.get("next_song") or self._config.stubbed_song()
        promoted_song_id = str(promoted_song["songId"])

        if not self._is_stubbed_song(promoted_song_id):
            await self._songs.mark_song_played(promoted_song_id)

        next_song = await self._select_song_for_next(exclude_song_ids={promoted_song_id})
        state["current_song"] = self._song_window(promoted_song, now)
        state["next_song"] = next_song
        state["poll"] = self._open_poll(state["current_song"], now)
        state["updated_at"] = now

    async def _select_song_for_current(self, exclude_song_ids: set[str]) -> dict[str, Any]:
        song = await self._songs.get_next_ready_song(exclude_song_ids)
        if song is None:
            return self._config.stubbed_song()

        await self._songs.mark_song_played(str(song["songId"]))
        return song

    async def _select_song_for_next(self, exclude_song_ids: set[str]) -> dict[str, Any]:
        song = await self._songs.get_next_ready_song(exclude_song_ids)
        if song is None:
            return self._config.stubbed_song()

        await self._songs.mark_song_queued(str(song["songId"]))
        return song

    def _song_window(self, song: dict[str, Any], start_at: int) -> dict[str, Any]:
        duration_ms = int(song["duration_ms"])
        return {
            "songId": song["songId"],
            "duration_ms": duration_ms,
            "start_at": start_at,
            "end_at": start_at + duration_ms,
        }

    def _open_poll(self, current_song: dict[str, Any], now: int) -> dict[str, Any]:
        close_at = max(
            now,
            int(current_song["end_at"]) - self._config.vote_close_lead_ms,
        )
        return {
            "options": self._config.poll_options(),
            "start_at": now,
            "end_at": close_at,
            "is_open": True,
        }

    async def _get_state(self) -> dict[str, Any]:
        if self._state_cache is not None:
            return self._state_cache

        stored = await self._ctx.storage.get(STATE_KEY)
        if isinstance(stored, dict):
            self._state_cache = stored
            return stored
        if stored is not None:
            cast_state = dict(stored)
            self._state_cache = cast_state
            return cast_state

        empty_state = {
            "current_song": None,
            "next_song": None,
            "poll": None,
            "updated_at": self._clock(),
        }
        self._state_cache = empty_state
        await self._persist_state(empty_state)
        return empty_state

    async def _persist_state(self, state: dict[str, Any]) -> None:
        self._state_cache = state
        await self._ctx.storage.put(STATE_KEY, state)
        await self._sync_alarm(state)

    async def _sync_alarm(self, state: dict[str, Any]) -> None:
        next_event_at = self._next_event_at(state)
        if next_event_at is None:
            await self._ctx.storage.deleteAlarm()
            return
        await self._ctx.storage.setAlarm(next_event_at)

    def _next_event_at(self, state: dict[str, Any]) -> int | None:
        event_times: list[int] = []

        current_song = state.get("current_song")
        if current_song:
            event_times.append(int(current_song["end_at"]))

        poll = state.get("poll")
        if poll and poll.get("is_open"):
            event_times.append(int(poll["end_at"]))

        if not event_times:
            return None
        return min(event_times)

    def _snapshot_response(self, state: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(
            {
                "current_song": state.get("current_song"),
                "next_song": state.get("next_song"),
                "poll": state.get("poll"),
                "updated_at": state.get("updated_at"),
            }
        )

    def _is_stubbed_song(self, song_id: str) -> bool:
        return song_id == STUBBED_SONG_ID
