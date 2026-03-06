import logging
import random
from typing import Any

from google.cloud.firestore import SERVER_TIMESTAMP

from pulsefm_playback_service.domain.protocols import EventPublisherProtocol, FirestoreRepositoryProtocol, RedisStateProtocol


class VoteCloseOrchestrator:
    def __init__(
        self,
        repository: FirestoreRepositoryProtocol,
        redis_state: RedisStateProtocol,
        events: EventPublisherProtocol,
        logger: logging.Logger | None = None,
    ) -> None:
        self.repository = repository
        self.redis_state = redis_state
        self.events = events
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _pick_winner(tallies: dict[str, Any]) -> str | None:
        if not tallies:
            return None
        max_votes = max(tallies.values())
        tied = [option for option, count in tallies.items() if count == max_votes]
        return random.choice(tied) if tied else None

    async def close_vote_state(self, state: dict[str, Any]) -> dict[str, Any]:
        vote_id = state.get("voteId")
        if not vote_id:
            raise ValueError("voteId missing from voteState/current")

        tallies = await self.redis_state.get_poll_tallies(vote_id)
        if not tallies:
            tallies = {option: 0 for option in (state.get("options") or [])}
        winner_option = self._pick_winner(tallies)

        window_doc = {
            **state,
            "status": "CLOSED",
            "winnerOption": winner_option,
            "tallies": tallies,
            "closedAt": SERVER_TIMESTAMP,
        }

        await self.repository.set_current_state(window_doc)
        await self.redis_state.set_poll_status(vote_id, "CLOSED")

        self.logger.info("Closed vote", extra={"voteId": vote_id, "winner": winner_option})
        self.events.publish_vote_close(vote_id, winner_option)
        return window_doc

    async def close_current_vote_if_matches(
        self,
        expected_vote_id: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        state = await self.repository.get_current_state()
        if not state:
            return {"action": "noop", "reason": "missing_state"}

        current_vote_id = state.get("voteId")
        current_version = int(state.get("version") or 0)
        current_status = state.get("status")

        if expected_vote_id is not None and current_vote_id != expected_vote_id:
            return {
                "action": "noop",
                "reason": "vote_mismatch",
                "voteId": current_vote_id,
                "version": current_version,
            }
        if expected_version is not None and current_version != expected_version:
            return {
                "action": "noop",
                "reason": "version_mismatch",
                "voteId": current_vote_id,
                "version": current_version,
            }
        if current_status != "OPEN":
            return {
                "action": "noop",
                "reason": "already_closed",
                "voteId": current_vote_id,
                "version": current_version,
            }

        await self.close_vote_state(state)
        return {"action": "closed", "voteId": current_vote_id, "version": current_version}
