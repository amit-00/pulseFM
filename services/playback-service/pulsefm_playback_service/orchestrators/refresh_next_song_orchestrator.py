import logging
from typing import Any

from fastapi import HTTPException, status

from pulsefm_playback_service.domain.protocols import EventPublisherProtocol, FirestoreRepositoryProtocol, RedisStateProtocol


class RefreshNextSongOrchestrator:
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

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        trigger_vote_id = payload.get("voteId")
        result = await self.repository.refresh_next_song(str(trigger_vote_id))

        if result is None:
            return {"status": "noop", "reason": "stale_version", "voteId": trigger_vote_id}

        self.logger.info(
            "Refreshed next song",
            extra={"voteId": result.get("voteId"), "version": result.get("version")},
        )

        redis_changed: bool | None = None
        if result.get("action") in {"updated", "noop"}:
            try:
                canonical_version = int(result.get("version") or 0)
                redis_changed = await self.redis_state.reconcile_next_song_snapshot(result)
                if redis_changed:
                    canonical_vote_id = str(result["voteId"])
                    canonical_duration_ms = int(result["durationMs"])
                    self.events.publish_next_song_changed(canonical_vote_id, canonical_duration_ms, canonical_version)
            except Exception:
                self.logger.exception("Failed to publish next-song change", extra={"voteId": result.get("voteId")})
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to publish next-song change",
                )

        self.logger.info(
            "Refresh next request handled",
            extra={"result": result, "redisChanged": redis_changed, "triggerVoteId": trigger_vote_id},
        )
        return {"status": "ok", **result}
