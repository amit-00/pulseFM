import logging
from typing import Any

from fastapi import HTTPException, status

from pulsefm_playback_service.domain.constants import VOTE_CLOSE_LEAD_SECONDS
from pulsefm_playback_service.domain.models import SongRotationResult
from pulsefm_playback_service.domain.protocols import (
    EventPublisherProtocol,
    FirestoreRepositoryProtocol,
    RedisStateProtocol,
    TaskSchedulerProtocol,
    VoteCloseOrchestratorProtocol,
)
from pulsefm_playback_service.utils.time import to_epoch_ms
from pulsefm_playback_service.utils.validation import validate_tick_version


class TickOrchestrator:
    def __init__(
        self,
        repository: FirestoreRepositoryProtocol,
        redis_state: RedisStateProtocol,
        events: EventPublisherProtocol,
        tasks: TaskSchedulerProtocol,
        vote_close: VoteCloseOrchestratorProtocol,
        logger: logging.Logger | None = None,
    ) -> None:
        self.repository = repository
        self.redis_state = redis_state
        self.events = events
        self.tasks = tasks
        self.vote_close = vote_close
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _build_playback_snapshot(rotation: SongRotationResult, window: dict[str, Any]) -> dict[str, Any]:
        return {
            "currentSong": {
                "voteId": rotation.vote_id,
                "startAt": to_epoch_ms(rotation.start_at),
                "endAt": to_epoch_ms(rotation.ends_at),
                "durationMs": rotation.duration_ms,
            },
            "nextSong": {
                "voteId": rotation.next_vote_id,
                "durationMs": rotation.next_duration_ms,
            },
            "poll": {
                "voteId": window.get("voteId"),
                "options": window.get("options"),
                "version": window.get("version"),
                "status": "OPEN",
                "endAt": to_epoch_ms(window.get("endAt")),
            },
        }

    async def _rotate_vote(self, song_duration_ms: int) -> dict[str, Any]:
        vote_duration_ms = max(0, song_duration_ms - (VOTE_CLOSE_LEAD_SECONDS * 1000))
        state = await self.repository.get_current_state()
        if state and state.get("status") == "OPEN":
            await self.vote_close.close_vote_state(state)
        version = int(state.get("version") or 0) + 1 if state else 1
        window = await self.repository.open_next_vote(version, vote_duration_ms)
        self.events.publish_vote_open(str(window["voteId"]), to_epoch_ms(window.get("endAt")))
        return window

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_version = validate_tick_version(payload)

        rotation = await self.repository.rotate_song(request_version)
        if rotation is None:
            return {"status": "noop", "reason": "stale_version", "requestVersion": request_version}

        self.logger.info(
            "Selected next song",
            extra={"voteId": rotation.next_vote_id, "stubbed": rotation.next_stubbed, "version": rotation.version},
        )

        try:
            window = await self._rotate_vote(rotation.duration_ms)
        except Exception:
            self.logger.exception("Failed to rotate vote")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to rotate vote")

        try:
            snapshot = self._build_playback_snapshot(rotation, window)
            await self.redis_state.open_poll_snapshot(
                str(window["voteId"]),
                window["startAt"],
                window["endAt"],
                rotation.duration_ms,
                window["options"],
                snapshot,
            )
        except Exception:
            self.logger.exception("Failed to update Redis playback snapshot", extra={"voteId": window.get("voteId")})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

        try:
            self.events.publish_changeover(rotation, request_version)
        except Exception:
            self.logger.exception("Failed to publish playback changeover", extra={"durationMs": rotation.duration_ms})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to publish changeover")
        self.logger.info("Published playback changeover", extra={"durationMs": rotation.duration_ms})

        self.tasks.schedule_next(rotation, window, request_version)
        return {"status": "ok", "version": request_version}
