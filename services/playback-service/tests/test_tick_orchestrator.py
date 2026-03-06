import asyncio
import unittest
from datetime import datetime, timezone

from pulsefm_playback_service.domain.models import SongRotationResult
from pulsefm_playback_service.orchestrators.tick_orchestrator import TickOrchestrator


class FakeRepository:
    def __init__(self, rotation=None, state=None, window=None):
        self.rotation = rotation
        self.state = state
        self.window = window

    async def rotate_song(self, request_version: int):
        return self.rotation

    async def get_current_state(self):
        return self.state

    async def open_next_vote(self, version: int, duration_ms: int):
        return self.window


class FakeRedisState:
    def __init__(self):
        self.calls = []

    async def open_poll_snapshot(self, vote_id, start_at, end_at, duration_ms, options, snapshot):
        self.calls.append((vote_id, start_at, end_at, duration_ms, options, snapshot))


class FakeEvents:
    def __init__(self):
        self.vote_open = []
        self.changeovers = []

    def publish_vote_open(self, vote_id, end_at_ms):
        self.vote_open.append((vote_id, end_at_ms))

    def publish_changeover(self, rotation, request_version):
        self.changeovers.append((rotation.vote_id, request_version))


class FakeTasks:
    def __init__(self):
        self.calls = []

    def schedule_next(self, rotation, window, request_version):
        self.calls.append((rotation.vote_id, window["voteId"], request_version))


class FakeVoteClose:
    def __init__(self):
        self.closed = []

    async def close_vote_state(self, state):
        self.closed.append(state)


class TickOrchestratorTests(unittest.TestCase):
    def test_tick_returns_noop_on_stale_version(self):
        orchestrator = TickOrchestrator(
            repository=FakeRepository(rotation=None),
            redis_state=FakeRedisState(),
            events=FakeEvents(),
            tasks=FakeTasks(),
            vote_close=FakeVoteClose(),
        )

        result = asyncio.run(orchestrator.run({"version": 10}))
        self.assertEqual(result, {"status": "noop", "reason": "stale_version", "requestVersion": 10})

    def test_tick_happy_path_runs_orchestration_flow(self):
        rotation = SongRotationResult(
            start_at=datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 3, 6, 12, 3, 0, tzinfo=timezone.utc),
            duration_ms=180000,
            vote_id="song-a",
            next_vote_id="song-b",
            next_duration_ms=175000,
            next_stubbed=False,
            version=7,
        )
        window = {
            "voteId": "vote-2",
            "startAt": datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc),
            "endAt": datetime(2026, 3, 6, 12, 2, 0, tzinfo=timezone.utc),
            "options": ["calm", "energy"],
            "version": 8,
        }
        vote_state = {"status": "OPEN", "version": 7, "voteId": "vote-1", "options": ["calm", "energy"]}

        redis_state = FakeRedisState()
        events = FakeEvents()
        tasks = FakeTasks()
        vote_close = FakeVoteClose()

        orchestrator = TickOrchestrator(
            repository=FakeRepository(rotation=rotation, state=vote_state, window=window),
            redis_state=redis_state,
            events=events,
            tasks=tasks,
            vote_close=vote_close,
        )

        result = asyncio.run(orchestrator.run({"version": 8}))

        self.assertEqual(result, {"status": "ok", "version": 8})
        self.assertEqual(len(vote_close.closed), 1)
        self.assertEqual(events.vote_open[0][0], "vote-2")
        self.assertEqual(len(redis_state.calls), 1)
        self.assertEqual(len(events.changeovers), 1)
        self.assertEqual(len(tasks.calls), 1)


if __name__ == "__main__":
    unittest.main()
