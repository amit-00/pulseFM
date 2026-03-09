from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import RuntimeConfig, STUBBED_SONG_ID  # noqa: E402
from orchestrator import PlaybackOrchestrator  # noqa: E402


class ManualClock:
    def __init__(self, now: int) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


class FakeStorage:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.alarm: int | None = None

    async def get(self, key: str):
        return self.values.get(key)

    async def put(self, key: str, value):
        self.values[key] = value

    async def setAlarm(self, timestamp_ms: int):
        self.alarm = timestamp_ms

    async def deleteAlarm(self):
        self.alarm = None


class FakeCtx:
    def __init__(self) -> None:
        self.storage = FakeStorage()


class FakeEnv:
    PLAYBACK_DB = None
    VOTE_OPTIONS = "energetic,dark,uplifting,cinematic,ambient"
    OPTIONS_PER_WINDOW = "4"
    STUBBED_DURATION_MS = "300000"
    VOTE_CLOSE_LEAD_SECONDS = "60"


class FakeSongRepository:
    def __init__(self, songs: list[dict[str, int | str]]) -> None:
        self.songs = songs
        self.queued_calls: list[str] = []
        self.played_calls: list[str] = []

    async def get_next_ready_song(self, exclude_song_ids: set[str] | None = None):
        excluded = exclude_song_ids or set()
        for song in self.songs:
            if song["status"] == "ready" and song["songId"] not in excluded:
                return {
                    "songId": str(song["songId"]),
                    "duration_ms": int(song["duration_ms"]),
                }
        return None

    async def mark_song_queued(self, song_id: str):
        self.queued_calls.append(song_id)
        for song in self.songs:
            if song["songId"] == song_id:
                song["status"] = "queued"

    async def mark_song_played(self, song_id: str):
        self.played_calls.append(song_id)
        for song in self.songs:
            if song["songId"] == song_id:
                song["status"] = "played"


class PlaybackOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def _make_orchestrator(self, songs: list[dict[str, int | str]], now: int):
        ctx = FakeCtx()
        env = FakeEnv()
        clock = ManualClock(now)
        repository = FakeSongRepository(songs)
        config = RuntimeConfig.from_env(
            {
                "VOTE_OPTIONS": env.VOTE_OPTIONS,
                "OPTIONS_PER_WINDOW": env.OPTIONS_PER_WINDOW,
                "STUBBED_DURATION_MS": env.STUBBED_DURATION_MS,
                "VOTE_CLOSE_LEAD_SECONDS": env.VOTE_CLOSE_LEAD_SECONDS,
            }
        )
        orchestrator = PlaybackOrchestrator(
            ctx=ctx,
            env=env,
            songs=repository,
            config=config,
            clock=clock,
        )
        return orchestrator, ctx, repository, clock

    async def test_start_initializes_current_next_and_poll(self):
        songs = [
            {"songId": "song-a", "duration_ms": 120_000, "status": "ready"},
            {"songId": "song-b", "duration_ms": 180_000, "status": "ready"},
        ]
        orchestrator, ctx, repo, _ = self._make_orchestrator(songs=songs, now=1_000_000)

        state = await orchestrator.start()

        self.assertEqual("song-a", state["current_song"]["songId"])
        self.assertEqual("song-b", state["next_song"]["songId"])
        self.assertTrue(state["poll"]["is_open"])
        self.assertEqual(4, len(state["poll"]["options"]))
        self.assertEqual(["song-a"], repo.played_calls)
        self.assertEqual(["song-b"], repo.queued_calls)
        self.assertEqual(state["poll"]["end_at"], ctx.storage.alarm)

    async def test_alarm_closes_poll_when_poll_end_is_due(self):
        songs = [
            {"songId": "song-a", "duration_ms": 120_000, "status": "ready"},
            {"songId": "song-b", "duration_ms": 180_000, "status": "ready"},
        ]
        orchestrator, ctx, _, clock = self._make_orchestrator(songs=songs, now=1_000_000)
        first_state = await orchestrator.start()

        clock.now = int(first_state["poll"]["end_at"]) + 1
        await orchestrator.handle_alarm()

        state = await orchestrator.state_snapshot()
        self.assertFalse(state["poll"]["is_open"])
        self.assertEqual("song-a", state["current_song"]["songId"])
        self.assertEqual(state["current_song"]["end_at"], ctx.storage.alarm)

    async def test_alarm_advances_song_and_opens_new_poll(self):
        songs = [
            {"songId": "song-a", "duration_ms": 120_000, "status": "ready"},
            {"songId": "song-b", "duration_ms": 180_000, "status": "ready"},
            {"songId": "song-c", "duration_ms": 240_000, "status": "ready"},
        ]
        orchestrator, ctx, repo, clock = self._make_orchestrator(songs=songs, now=1_000_000)
        started_state = await orchestrator.start()

        clock.now = int(started_state["current_song"]["end_at"]) + 1
        await orchestrator.handle_alarm()

        state = await orchestrator.state_snapshot()
        self.assertEqual("song-b", state["current_song"]["songId"])
        self.assertEqual("song-c", state["next_song"]["songId"])
        self.assertTrue(state["poll"]["is_open"])
        self.assertEqual(["song-a", "song-b"], repo.played_calls)
        self.assertEqual(["song-b", "song-c"], repo.queued_calls)
        self.assertEqual(state["poll"]["end_at"], ctx.storage.alarm)

    async def test_start_uses_stubbed_song_when_no_ready_songs(self):
        orchestrator, _, repo, _ = self._make_orchestrator(songs=[], now=1_000_000)

        state = await orchestrator.start()

        self.assertEqual(STUBBED_SONG_ID, state["current_song"]["songId"])
        self.assertEqual(STUBBED_SONG_ID, state["next_song"]["songId"])
        self.assertTrue(state["poll"]["is_open"])
        self.assertEqual([], repo.played_calls)
        self.assertEqual([], repo.queued_calls)


if __name__ == "__main__":
    unittest.main()
