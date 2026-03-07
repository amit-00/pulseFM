from __future__ import annotations

import uuid
from typing import Any

from config import RuntimeConfig
from helpers import parse_int, read_value, utc_ms
from song_repository import SongRepository

STATE_KEY = "playback-state-v2"
EVENT_TYPE_TICK = "tick"
EVENT_TYPE_CLOSE_POLL = "close_poll"


class PlaybackOrchestrator:
    def __init__(self, ctx, env) -> None:
        self._ctx = ctx
        self._config = RuntimeConfig.from_env(env)
        self._songs = SongRepository(read_value(env, "PLAYBACK_DB"))
        self._state_cache: dict[str, Any] | None = None

    async def state_snapshot(self) -> dict[str, Any]:
        state = await self._get_state()
        await self._ensure_startup_tick(state)
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
        event_type = read_value(event, "type")

        if event_type == EVENT_TYPE_TICK:
            await self._run_tick(state)
            return

        if event_type == EVENT_TYPE_CLOSE_POLL:
            await self._run_close_poll(state, event)

    async def _run_tick(self, state: dict[str, Any]) -> None:
        now = utc_ms()
        current_version = int(state.get("version") or 0)
        promoted_song = state.get("nextSong") or self._config.stubbed_song()

        promoted_vote_id = str(read_value(promoted_song, "voteId", "stubbed"))
        promoted_duration_ms = parse_int(read_value(promoted_song, "durationMs"), self._config.stubbed_duration_ms)
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
        previous_poll_version = int(read_value(previous_poll, "version", 0) or 0)
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
                "id": self._tick_event_id(next_version + 1),
                "type": EVENT_TYPE_TICK,
                "dueAt": int(state["currentSong"]["endAt"]),
                "payload": {"version": next_version + 1},
            },
        )

    async def _run_close_poll(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        poll = state.get("poll")
        if not poll:
            return

        payload = read_value(event, "payload", {}) or {}
        expected_vote_id = str(read_value(payload, "voteId", ""))
        expected_version = parse_int(read_value(payload, "version"), 0) or 0

        if poll.get("status") != "OPEN":
            return
        if str(read_value(poll, "voteId", "")) != expected_vote_id:
            return
        if int(read_value(poll, "version", 0) or 0) != expected_version:
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

        next_due_at = min(parse_int(read_value(event, "dueAt"), 0) or 0 for event in events)
        await self._ctx.storage.setAlarm(next_due_at)

    async def _ensure_startup_tick(self, state: dict[str, Any]) -> None:
        has_tick_event = any(read_value(event, "type") == EVENT_TYPE_TICK for event in state.get("scheduledEvents", []))
        if has_tick_event:
            return

        first_tick_version = int(state.get("version") or 0) + 1
        due_at = utc_ms() + self._config.startup_tick_delay_ms
        self._enqueue_event(
            state,
            {
                "id": self._tick_event_id(first_tick_version),
                "type": EVENT_TYPE_TICK,
                "dueAt": due_at,
                "payload": {"version": first_tick_version},
            },
        )
        state["updatedAt"] = utc_ms()
        await self._persist_state(state)

    def _split_due_events(self, events: list[dict[str, Any]], now_ms: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        due_events: list[dict[str, Any]] = []
        future_events: list[dict[str, Any]] = []

        for event in events:
            due_at = parse_int(read_value(event, "dueAt"), 0) or 0
            if due_at <= now_ms:
                due_events.append(event)
            else:
                future_events.append(event)

        due_events.sort(key=lambda event: parse_int(read_value(event, "dueAt"), 0) or 0)
        return due_events, future_events

    def _enqueue_event(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        target_id = str(read_value(event, "id", ""))
        deduped = [existing for existing in state.get("scheduledEvents", []) if read_value(existing, "id") != target_id]
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

    def _tick_event_id(self, version: int) -> str:
        return f"tick:{version}"

    def _close_poll_event_id(self, vote_id: str, version: int) -> str:
        return f"close:{vote_id}:{version}"
