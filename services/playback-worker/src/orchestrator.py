from __future__ import annotations

import uuid
from typing import Any

from config import RuntimeConfig
from helpers import parse_int, utc_ms
from song_repository import SongRepository

STATE_KEY = "playback-state-v2"
EVENT_TYPE_NEXT_SONG = "next_song"
EVENT_TYPE_CLOSE_POLL = "close_poll"


class PlaybackOrchestrator:
    def __init__(self, ctx, env) -> None:
        self._ctx = ctx
        self._config = RuntimeConfig.from_env(
            {
                "VOTE_OPTIONS": getattr(env, "VOTE_OPTIONS", ""),
                "OPTIONS_PER_WINDOW": getattr(env, "OPTIONS_PER_WINDOW", "4"),
                "STUBBED_DURATION_MS": getattr(env, "STUBBED_DURATION_MS", "300000"),
                "VOTE_CLOSE_LEAD_SECONDS": getattr(env, "VOTE_CLOSE_LEAD_SECONDS", "60"),
                "STARTUP_NEXT_SONG_DELAY_SECONDS": getattr(env, "STARTUP_NEXT_SONG_DELAY_SECONDS", "5"),
            }
        )
        self._songs = SongRepository(env.PLAYBACK_DB)
        self._state_cache: dict[str, Any] | None = None

    async def state_snapshot(self) -> dict[str, Any]:
        state = await self._get_state()
        await self._ensure_startup_next_song(state)
        return self._snapshot_response(state)

    async def handle_alarm(self) -> None:
        state = await self._get_state()
        due_events, future_events = self._split_due_events(state.get("scheduledEvents", []), utc_ms())

        if not due_events:
            await self._sync_alarm(state)
            return

        state["scheduledEvents"] = future_events
        for event in due_events:
            await self._handle_event(state, event)

        state["updatedAt"] = utc_ms()
        await self._persist_state(state)

    async def _handle_event(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        event_type = event.get("type")

        if event_type == EVENT_TYPE_NEXT_SONG:
            await self._run_next_song(state)
            return

        if event_type == EVENT_TYPE_CLOSE_POLL:
            await self._run_close_poll(state, event)

    async def _run_next_song(self, state: dict[str, Any]) -> None:
        now = utc_ms()
        current_version = int(state.get("version") or 0)
        promoted_song = state.get("nextSong") or self._config.stubbed_song()

        promoted_vote_id = str(promoted_song.get("voteId", "stubbed"))
        promoted_duration_ms = parse_int(promoted_song.get("durationMs"), self._config.stubbed_duration_ms)
        promoted_duration_ms = promoted_duration_ms or self._config.stubbed_duration_ms

        if promoted_vote_id != "stubbed":
            await self._songs.mark_song_status(promoted_vote_id, "played")

        next_candidate = await self._songs.select_next_ready_song(promoted_vote_id)
        if next_candidate:
            await self._songs.mark_song_status(str(next_candidate["voteId"]), "queued")
            state["nextSong"] = next_candidate
        else:
            state["nextSong"] = self._config.stubbed_song()

        state["currentSong"] = {
            "voteId": promoted_vote_id,
            "startAt": now,
            "endAt": now + promoted_duration_ms,
            "durationMs": promoted_duration_ms,
        }

        previous_poll = state.get("poll")
        if previous_poll and previous_poll.get("status") == "OPEN":
            previous_poll["status"] = "CLOSED"
            previous_poll["closedAt"] = now

        poll_duration_ms = max(0, promoted_duration_ms - self._config.vote_close_lead_ms)
        previous_poll_version = int((previous_poll or {}).get("version") or 0)
        poll_version = previous_poll_version + 1
        poll_vote_id = str(uuid.uuid4())
        poll_options = self._config.pick_vote_options()

        state["poll"] = {
            "voteId": poll_vote_id,
            "status": "OPEN",
            "startAt": now,
            "endAt": now + poll_duration_ms,
            "durationMs": poll_duration_ms,
            "options": poll_options,
            "tallies": {option: 0 for option in poll_options},
            "version": poll_version,
        }

        next_version = current_version + 1
        state["version"] = next_version
        state["updatedAt"] = now

        self._enqueue_event(
            state,
            {
                "id": self._close_poll_event_id(poll_vote_id, poll_version),
                "type": EVENT_TYPE_CLOSE_POLL,
                "dueAt": int(state["poll"]["endAt"]),
                "payload": {"voteId": poll_vote_id, "version": poll_version},
            },
        )

        self._enqueue_event(
            state,
            {
                "id": self._next_song_event_id(next_version + 1),
                "type": EVENT_TYPE_NEXT_SONG,
                "dueAt": int(state["currentSong"]["endAt"]),
                "payload": {"version": next_version + 1},
            },
        )

    async def _run_close_poll(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        poll = state.get("poll")
        if not poll:
            return

        payload = event.get("payload", {}) or {}
        expected_vote_id = str(payload.get("voteId", ""))
        expected_version = parse_int(payload.get("version"), 0) or 0

        if poll.get("status") != "OPEN":
            return
        if str(poll.get("voteId", "")) != expected_vote_id:
            return
        if int(poll.get("version", 0) or 0) != expected_version:
            return

        poll["status"] = "CLOSED"
        poll["closedAt"] = utc_ms()

    async def _get_state(self) -> dict[str, Any]:
        if self._state_cache is not None:
            return self._state_cache

        stored = await self._ctx.storage.get(STATE_KEY)
        if stored is None:
            initial_state = {
                "version": 0,
                "currentSong": None,
                "nextSong": self._config.stubbed_song(),
                "poll": None,
                "scheduledEvents": [],
                "updatedAt": utc_ms(),
            }
            self._state_cache = initial_state
            await self._persist_state(initial_state)
            return initial_state

        if isinstance(stored, dict):
            self._state_cache = stored
        else:
            self._state_cache = dict(stored)
        return self._state_cache

    async def _persist_state(self, state: dict[str, Any]) -> None:
        self._state_cache = state
        await self._ctx.storage.put(STATE_KEY, state)
        await self._sync_alarm(state)

    async def _sync_alarm(self, state: dict[str, Any]) -> None:
        events = state.get("scheduledEvents", [])
        if not events:
            await self._ctx.storage.deleteAlarm()
            return

        next_due_at = min(parse_int(event.get("dueAt"), 0) or 0 for event in events)
        await self._ctx.storage.setAlarm(next_due_at)

    async def _ensure_startup_next_song(self, state: dict[str, Any]) -> None:
        has_next_song_event = any(
            event.get("type") == EVENT_TYPE_NEXT_SONG
            for event in state.get("scheduledEvents", [])
        )
        if has_next_song_event:
            return

        await self._prime_startup_next_song(state)

        first_next_song_version = int(state.get("version") or 0) + 1
        due_at = utc_ms() + self._config.startup_next_song_delay_ms
        self._enqueue_event(
            state,
            {
                "id": self._next_song_event_id(first_next_song_version),
                "type": EVENT_TYPE_NEXT_SONG,
                "dueAt": due_at,
                "payload": {"version": first_next_song_version},
            },
        )
        state["updatedAt"] = utc_ms()
        await self._persist_state(state)

    async def _prime_startup_next_song(self, state: dict[str, Any]) -> None:
        is_first_cycle = int(state.get("version") or 0) == 0 and state.get("currentSong") is None
        if not is_first_cycle:
            return

        first_ready_song = await self._songs.select_next_ready_song(None)
        if not first_ready_song:
            state["nextSong"] = self._config.stubbed_song()
            return

        await self._songs.mark_song_status(str(first_ready_song["voteId"]), "queued")
        state["nextSong"] = first_ready_song

    def _split_due_events(
        self,
        events: list[dict[str, Any]],
        now_ms: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        due_events: list[dict[str, Any]] = []
        future_events: list[dict[str, Any]] = []

        for event in events:
            due_at = parse_int(event.get("dueAt"), 0) or 0
            if due_at <= now_ms:
                due_events.append(event)
            else:
                future_events.append(event)

        due_events.sort(key=lambda event: parse_int(event.get("dueAt"), 0) or 0)
        return due_events, future_events

    def _enqueue_event(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        target_id = str(event.get("id", ""))
        deduped = [
            existing
            for existing in state.get("scheduledEvents", [])
            if existing.get("id") != target_id
        ]
        deduped.append(event)
        state["scheduledEvents"] = deduped

    def _snapshot_response(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": state.get("version"),
            "currentSong": state.get("currentSong"),
            "nextSong": state.get("nextSong"),
            "poll": state.get("poll"),
            "updatedAt": state.get("updatedAt"),
        }

    def _next_song_event_id(self, version: int) -> str:
        return f"next_song:{version}"

    def _close_poll_event_id(self, vote_id: str, version: int) -> str:
        return f"close:{vote_id}:{version}"
