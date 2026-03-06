import asyncio
import unittest

from pulsefm_playback_service.orchestrators.vote_close_orchestrator import VoteCloseOrchestrator


class FakeRepository:
    def __init__(self, state):
        self.state = state
        self.saved = None

    async def get_current_state(self):
        return self.state

    async def set_current_state(self, state):
        self.saved = state


class FakeRedisState:
    def __init__(self, tallies):
        self.tallies = tallies
        self.status_updates = []

    async def get_poll_tallies(self, vote_id: str):
        return self.tallies

    async def set_poll_status(self, vote_id: str, status: str):
        self.status_updates.append((vote_id, status))


class FakeEvents:
    def __init__(self):
        self.closes = []

    def publish_vote_close(self, vote_id: str, winner_option=None):
        self.closes.append((vote_id, winner_option))


class VoteCloseOrchestratorTests(unittest.TestCase):
    def test_vote_close_returns_vote_mismatch_noop(self):
        orchestrator = VoteCloseOrchestrator(
            repository=FakeRepository({"voteId": "current", "status": "OPEN", "version": 5}),
            redis_state=FakeRedisState({"a": 1}),
            events=FakeEvents(),
        )

        result = asyncio.run(orchestrator.close_current_vote_if_matches(expected_vote_id="different", expected_version=5))

        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["reason"], "vote_mismatch")

    def test_vote_close_closes_current_vote_and_publishes_event(self):
        repo = FakeRepository({"voteId": "current", "status": "OPEN", "version": 5, "options": ["a", "b"]})
        redis_state = FakeRedisState({"a": 2, "b": 1})
        events = FakeEvents()
        orchestrator = VoteCloseOrchestrator(repository=repo, redis_state=redis_state, events=events)

        result = asyncio.run(orchestrator.close_current_vote_if_matches(expected_vote_id="current", expected_version=5))

        self.assertEqual(result, {"action": "closed", "voteId": "current", "version": 5})
        self.assertIsNotNone(repo.saved)
        self.assertEqual(repo.saved["status"], "CLOSED")
        self.assertEqual(repo.saved["winnerOption"], "a")
        self.assertEqual(redis_state.status_updates, [("current", "CLOSED")])
        self.assertEqual(events.closes, [("current", "a")])


if __name__ == "__main__":
    unittest.main()
