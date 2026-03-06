import asyncio
import unittest

from pulsefm_playback_service.orchestrators.refresh_next_song_orchestrator import RefreshNextSongOrchestrator


class FakeRepository:
    def __init__(self, result):
        self.result = result

    async def refresh_next_song(self, trigger_vote_id: str):
        return self.result


class FakeRedisState:
    def __init__(self, changed: bool):
        self.changed = changed

    async def reconcile_next_song_snapshot(self, result):
        return self.changed


class FakeEvents:
    def __init__(self):
        self.next_song = []

    def publish_next_song_changed(self, vote_id: str, duration_ms: int, version: int):
        self.next_song.append((vote_id, duration_ms, version))


class RefreshNextSongOrchestratorTests(unittest.TestCase):
    def test_refresh_next_song_publishes_when_redis_changes(self):
        result = {"action": "updated", "voteId": "next-1", "durationMs": 123000, "version": 9}
        events = FakeEvents()
        orchestrator = RefreshNextSongOrchestrator(
            repository=FakeRepository(result),
            redis_state=FakeRedisState(changed=True),
            events=events,
        )

        response = asyncio.run(orchestrator.run({"voteId": "trigger-1"}))

        self.assertEqual(response, {"status": "ok", **result})
        self.assertEqual(events.next_song, [("next-1", 123000, 9)])

    def test_refresh_next_song_skips_publish_when_redis_unchanged(self):
        result = {"action": "noop", "reason": "next_not_stubbed", "voteId": "next-1", "durationMs": 123000, "version": 9}
        events = FakeEvents()
        orchestrator = RefreshNextSongOrchestrator(
            repository=FakeRepository(result),
            redis_state=FakeRedisState(changed=False),
            events=events,
        )

        response = asyncio.run(orchestrator.run({"voteId": "trigger-1"}))

        self.assertEqual(response, {"status": "ok", **result})
        self.assertEqual(events.next_song, [])


if __name__ == "__main__":
    unittest.main()
