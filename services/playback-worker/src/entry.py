from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any

from workers import DurableObject, Request, Response, WorkerEntrypoint

STATE_KEY = "playback-state-v1"
DEFAULT_STUBBED_DURATION_MS = 300_000
DEFAULT_VOTE_CLOSE_LEAD_SECONDS = 60
DEFAULT_VOTE_OPTIONS = ["energetic", "dark", "uplifting", "cinematic"]

FORWARDED_PATHS = {
    "/tick",
    "/vote/close",
    "/next/refresh",
    "/songs/upsert",
    "/state",
}


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _parse_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _map_get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return value.get(key, default)
    except Exception:
        try:
            return getattr(value, key)
        except Exception:
            pass
        try:
            return value[key]
        except Exception:
            return default


class PlaybackStateDurableObject(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self._cache: dict[str, Any] | None = None

    async def fetch(self, request: Request) -> Response:
        from urllib.parse import urlparse

        parsed = urlparse(request.url)
        method = request.method.upper()
        path = parsed.path

        if method == "GET" and path == "/health":
            return Response.json({"status": "healthy"})

        if method == "GET" and path == "/state":
            state = await self._get_state()
            return Response.json(state)

        if method != "POST":
            return Response.json({"error": "method_not_allowed"}, status=405)

        payload = {}
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        if path == "/tick":
            version = _parse_int(_map_get(payload, "version"))
            if version is None or version <= 0:
                return Response.json({"error": "version must be a positive integer"}, status=400)
            result = await self._handle_tick(version, source="http")
            return Response.json(result)

        if path == "/vote/close":
            vote_id = str(_map_get(payload, "voteId", "")).strip()
            version = _parse_int(_map_get(payload, "version"))
            if not vote_id:
                return Response.json({"error": "voteId is required"}, status=400)
            if version is None or version <= 0:
                return Response.json({"error": "version must be a positive integer"}, status=400)

            result = await self._handle_close_vote(vote_id, version, source="http")
            return Response.json({"status": "ok", **result})

        if path == "/next/refresh":
            trigger_vote_id = _map_get(payload, "voteId")
            trigger_vote_id = str(trigger_vote_id) if trigger_vote_id is not None else None
            result = await self._handle_refresh_next_song(trigger_vote_id)
            return Response.json(result)

        if path == "/songs/upsert":
            vote_id = str(_map_get(payload, "voteId", "")).strip()
            duration_ms = _parse_int(_map_get(payload, "durationMs"))
            status = str(_map_get(payload, "status", "ready"))
            created_at = _parse_int(_map_get(payload, "createdAt"), _utc_ms())

            if not vote_id:
                return Response.json({"error": "voteId is required"}, status=400)
            if duration_ms is None or duration_ms <= 0:
                return Response.json({"error": "durationMs must be positive"}, status=400)
            if status not in {"ready", "queued", "played"}:
                return Response.json({"error": "status must be ready|queued|played"}, status=400)

            await self._upsert_song(vote_id, duration_ms, status, created_at)
            return Response.json({"status": "ok", "voteId": vote_id, "durationMs": duration_ms, "songStatus": status})

        return Response.json({"error": "not_found"}, status=404)

    async def alarm(self, alarm_info=None):
        due_events = await self._pop_due_events(_utc_ms())
        for event in due_events:
            event_type = _map_get(event, "type")
            payload = _map_get(event, "payload", {})
            if event_type == "tick":
                version = _parse_int(_map_get(payload, "version"))
                if version is not None and version > 0:
                    await self._handle_tick(version, source="alarm")
            elif event_type == "closeVote":
                vote_id = str(_map_get(payload, "voteId", "")).strip()
                version = _parse_int(_map_get(payload, "version"))
                if vote_id and version is not None and version > 0:
                    await self._handle_close_vote(vote_id, version, source="alarm")

    async def _handle_tick(self, request_version: int, source: str) -> dict[str, Any]:
        state = await self._get_state()

        if request_version <= int(state["version"]):
            return {
                "status": "noop",
                "reason": "stale_version",
                "requestVersion": request_version,
                "version": state["version"],
            }

        now = _utc_ms()
        promoted = state.get("nextSong") or self._stubbed_song()

        if promoted.get("voteId") != "stubbed":
            await self._update_song_status(str(promoted["voteId"]), "played")

        next_candidate = await self._select_ready_song(str(promoted.get("voteId", "")) or None)
        if next_candidate:
            await self._update_song_status(str(next_candidate["voteId"]), "queued")
            state["nextSong"] = next_candidate
        else:
            state["nextSong"] = self._stubbed_song()

        promoted_duration_ms = int(promoted.get("durationMs") or self._stubbed_duration_ms())
        state["currentSong"] = {
            "voteId": promoted.get("voteId", "stubbed"),
            "startAt": now,
            "endAt": now + promoted_duration_ms,
            "durationMs": promoted_duration_ms,
        }

        poll = state.get("poll")
        if poll and poll.get("status") == "OPEN":
            poll["status"] = "CLOSED"
            poll["closedAt"] = now

        poll_duration_ms = max(0, promoted_duration_ms - self._vote_close_lead_ms())
        poll_version = int((state.get("poll") or {}).get("version") or 0) + 1
        options = self._sample_vote_options()
        vote_id = str(uuid.uuid4())

        state["poll"] = {
            "voteId": vote_id,
            "status": "OPEN",
            "startAt": now,
            "endAt": now + poll_duration_ms,
            "durationMs": poll_duration_ms,
            "options": options,
            "tallies": {option: 0 for option in options},
            "version": poll_version,
        }

        state["version"] = request_version
        state["updatedAt"] = now

        self._enqueue_event(
            state,
            {
                "id": self._close_vote_event_id(vote_id, poll_version),
                "type": "closeVote",
                "dueAt": int(state["poll"]["endAt"]),
                "payload": {"voteId": vote_id, "version": poll_version},
            },
        )

        self._enqueue_event(
            state,
            {
                "id": self._tick_event_id(request_version + 1),
                "type": "tick",
                "dueAt": int(state["currentSong"]["endAt"]),
                "payload": {"version": request_version + 1},
            },
        )

        await self._persist_state(state)

        response: dict[str, Any] = {
            "status": "ok",
            "version": request_version,
            "requestVersion": request_version,
        }
        if source == "alarm":
            response["reason"] = "scheduled"
        return response

    async def _handle_close_vote(self, vote_id: str, version: int, source: str) -> dict[str, Any]:
        state = await self._get_state()
        poll = state.get("poll")

        if not poll:
            return {"action": "noop", "reason": "missing_poll"}
        if poll.get("voteId") != vote_id:
            return {"action": "noop", "reason": "vote_mismatch", "voteId": poll.get("voteId"), "version": poll.get("version")}
        if int(poll.get("version") or 0) != version:
            return {"action": "noop", "reason": "version_mismatch", "voteId": poll.get("voteId"), "version": poll.get("version")}
        if poll.get("status") != "OPEN":
            return {"action": "noop", "reason": "already_closed", "voteId": poll.get("voteId"), "version": poll.get("version")}

        poll["status"] = "CLOSED"
        poll["closedAt"] = _utc_ms()
        state["updatedAt"] = _utc_ms()
        state["scheduledEvents"] = [
            event for event in state.get("scheduledEvents", [])
            if _map_get(event, "id") != self._close_vote_event_id(vote_id, version)
        ]

        await self._persist_state(state)

        response = {"action": "closed", "voteId": poll.get("voteId"), "version": poll.get("version")}
        if source == "alarm":
            response["reason"] = "scheduled"
        return response

    async def _handle_refresh_next_song(self, trigger_vote_id: str | None) -> dict[str, Any]:
        state = await self._get_state()
        next_song = state.get("nextSong") or self._stubbed_song()

        if next_song.get("voteId") != "stubbed":
            return {
                "status": "ok",
                "action": "noop",
                "reason": "next_not_stubbed",
                "voteId": next_song.get("voteId"),
                "durationMs": next_song.get("durationMs"),
                "version": state.get("version"),
                "triggerVoteId": trigger_vote_id,
            }

        excluded_vote_id = _map_get(state.get("currentSong"), "voteId")
        candidate = await self._select_ready_song(str(excluded_vote_id) if excluded_vote_id else None)
        if not candidate:
            return {
                "status": "ok",
                "action": "noop",
                "reason": "no_ready_song",
                "voteId": next_song.get("voteId"),
                "version": state.get("version"),
                "triggerVoteId": trigger_vote_id,
            }

        await self._update_song_status(str(candidate["voteId"]), "queued")
        state["nextSong"] = candidate
        state["updatedAt"] = _utc_ms()
        await self._persist_state(state)

        return {
            "status": "ok",
            "action": "updated",
            "voteId": candidate["voteId"],
            "durationMs": candidate["durationMs"],
            "version": state.get("version"),
            "triggerVoteId": trigger_vote_id,
        }

    async def _get_state(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache

        stored = await self.ctx.storage.get(STATE_KEY)
        if stored is not None:
            if isinstance(stored, dict):
                self._cache = stored
            else:
                try:
                    self._cache = dict(stored)
                except Exception:
                    self._cache = stored
            return self._cache

        initial = {
            "version": 0,
            "currentSong": None,
            "nextSong": self._stubbed_song(),
            "poll": None,
            "scheduledEvents": [],
            "updatedAt": _utc_ms(),
        }
        self._cache = initial
        await self._persist_state(initial)
        return initial

    async def _persist_state(self, state: dict[str, Any]) -> None:
        self._cache = state
        await self.ctx.storage.put(STATE_KEY, state)
        await self._sync_alarm(state)

    async def _pop_due_events(self, now_ms: int) -> list[dict[str, Any]]:
        state = await self._get_state()
        due = []
        future = []
        for event in state.get("scheduledEvents", []):
            event_due_at = _parse_int(_map_get(event, "dueAt"), 0) or 0
            if event_due_at <= now_ms:
                due.append(dict(event))
            else:
                future.append(dict(event))

        if due:
            state["scheduledEvents"] = future
            state["updatedAt"] = _utc_ms()
            await self._persist_state(state)

        due.sort(key=lambda event: _parse_int(_map_get(event, "dueAt"), 0) or 0)
        return due

    async def _sync_alarm(self, state: dict[str, Any]) -> None:
        events = state.get("scheduledEvents", [])
        if not events:
            await self.ctx.storage.deleteAlarm()
            return

        next_due_at = min((_parse_int(_map_get(event, "dueAt"), 0) or 0) for event in events)
        await self.ctx.storage.setAlarm(next_due_at)

    def _enqueue_event(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        existing_events = [e for e in state.get("scheduledEvents", []) if _map_get(e, "id") != _map_get(event, "id")]
        existing_events.append(event)
        state["scheduledEvents"] = existing_events

    def _tick_event_id(self, version: int) -> str:
        return f"tick:{version}"

    def _close_vote_event_id(self, vote_id: str, version: int) -> str:
        return f"close:{vote_id}:{version}"

    def _stubbed_duration_ms(self) -> int:
        configured = _parse_int(_map_get(self.env, "STUBBED_DURATION_MS"))
        if configured is None or configured <= 0:
            return DEFAULT_STUBBED_DURATION_MS
        return configured

    def _stubbed_song(self) -> dict[str, Any]:
        return {"voteId": "stubbed", "durationMs": self._stubbed_duration_ms()}

    def _vote_close_lead_ms(self) -> int:
        configured = _parse_int(_map_get(self.env, "VOTE_CLOSE_LEAD_SECONDS"))
        seconds = configured if configured is not None and configured >= 0 else DEFAULT_VOTE_CLOSE_LEAD_SECONDS
        return int(seconds) * 1000

    def _parse_vote_options(self) -> list[str]:
        raw_options = str(_map_get(self.env, "VOTE_OPTIONS", ""))
        parsed = [item.strip() for item in raw_options.split(",") if item.strip()]
        if parsed:
            return parsed
        return list(DEFAULT_VOTE_OPTIONS)

    def _sample_vote_options(self) -> list[str]:
        requested = _parse_int(_map_get(self.env, "OPTIONS_PER_WINDOW"), 4) or 4
        pool = self._parse_vote_options()
        if len(pool) <= requested:
            return pool
        return random.sample(pool, requested)

    async def _select_ready_song(self, exclude_vote_id: str | None) -> dict[str, Any] | None:
        if exclude_vote_id:
            statement = self.env.PLAYBACK_DB.prepare(
                "SELECT id, duration_ms FROM songs WHERE status = 'ready' AND id != ? ORDER BY created_at DESC LIMIT 1"
            ).bind(exclude_vote_id)
        else:
            statement = self.env.PLAYBACK_DB.prepare(
                "SELECT id, duration_ms FROM songs WHERE status = 'ready' ORDER BY created_at DESC LIMIT 1"
            )

        result = await statement.run()
        rows = _map_get(result, "results", []) or []
        if not rows:
            return None

        first = rows[0]
        vote_id = _map_get(first, "id")
        duration_ms = _parse_int(_map_get(first, "duration_ms"))
        if not vote_id or duration_ms is None or duration_ms <= 0:
            return None

        return {"voteId": str(vote_id), "durationMs": duration_ms}

    async def _update_song_status(self, vote_id: str, status: str) -> None:
        await self.env.PLAYBACK_DB.prepare(
            "UPDATE songs SET status = ?, updated_at = ? WHERE id = ?"
        ).bind(status, _utc_ms(), vote_id).run()

    async def _upsert_song(self, vote_id: str, duration_ms: int, status: str, created_at: int) -> None:
        await self.env.PLAYBACK_DB.prepare(
            "INSERT INTO songs (id, status, duration_ms, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status = excluded.status, "
            "duration_ms = excluded.duration_ms, "
            "created_at = excluded.created_at, "
            "updated_at = excluded.updated_at"
        ).bind(vote_id, status, duration_ms, created_at, _utc_ms()).run()


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        from urllib.parse import urlparse

        parsed = urlparse(request.url)
        path = parsed.path

        if request.method.upper() == "GET" and path == "/health":
            return Response.json({"status": "healthy", "trustModel": "network"})

        if path not in FORWARDED_PATHS:
            return Response.json({"error": "not_found"}, status=404)

        durable_object_id = self.env.PLAYBACK_STATE.idFromName("main")
        stub = self.env.PLAYBACK_STATE.get(durable_object_id)
        return await stub.fetch(request)
