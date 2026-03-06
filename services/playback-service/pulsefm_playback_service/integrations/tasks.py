import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from pulsefm_tasks.client import enqueue_json_task_with_delay

from pulsefm_playback_service.config import Settings
from pulsefm_playback_service.domain.constants import DEFAULT_STARTUP_DELAY_SECONDS, VOTE_CLOSE_LEAD_SECONDS
from pulsefm_playback_service.domain.models import SongRotationResult
from pulsefm_playback_service.utils.time import parse_timestamp, remaining_delay_seconds, utc_now


class TaskScheduler:
    def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    @property
    def has_tick_url(self) -> bool:
        return bool(self.settings.playback_tick_url)

    def _tick_url(self) -> str:
        return self.settings.playback_tick_url.rstrip("/") + "/tick"

    def _vote_close_url(self) -> str:
        return self.settings.playback_tick_url.rstrip("/") + "/vote/close"

    @staticmethod
    def build_tick_task_id(vote_id: str | None, ends_at: datetime | None, version: int | None = None) -> str:
        suffix = vote_id or ""
        timestamp = str(int(ends_at.timestamp())) if ends_at else ""
        version_suffix = str(version) if version is not None else ""
        return f"playback-{suffix}-{timestamp}-{version_suffix}"

    @staticmethod
    def build_vote_close_task_id(vote_id: str, version: int) -> str:
        return f"vote-close-{vote_id}-{version}"

    def schedule_startup_tick(self, station: dict[str, Any]) -> None:
        ends_at = station.get("endAt")
        vote_id = station.get("voteId")
        current_version = int(station.get("version") or 0)
        next_version = current_version + 1

        delay_seconds = remaining_delay_seconds(ends_at) or DEFAULT_STARTUP_DELAY_SECONDS
        parsed_end_at = None
        if ends_at:
            try:
                parsed_end_at = parse_timestamp(ends_at)
            except ValueError:
                parsed_end_at = None

        task_id = self.build_tick_task_id(vote_id, parsed_end_at, next_version)
        enqueue_json_task_with_delay(
            self.settings.playback_queue,
            self._tick_url(),
            {"version": next_version},
            delay_seconds,
            task_id=task_id,
            ignore_already_exists=True,
        )
        self.logger.info(
            "Startup tick scheduled",
            extra={"voteId": vote_id, "delaySeconds": delay_seconds, "version": next_version},
        )

    def schedule_next(self, rotation: SongRotationResult, window: dict[str, Any], request_version: int) -> None:
        if not self.settings.playback_tick_url:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PLAYBACK_TICK_URL is required")

        close_vote_id = window.get("voteId")
        close_version = int(window.get("version") or 0)
        try:
            close_delay = max(0.0, (window["endAt"] - utc_now()).total_seconds())
        except Exception:
            vote_duration_ms = max(0, rotation.duration_ms - (VOTE_CLOSE_LEAD_SECONDS * 1000))
            close_delay = max(0.0, vote_duration_ms / 1000)

        enqueue_json_task_with_delay(
            self.settings.playback_queue,
            self._vote_close_url(),
            {"voteId": close_vote_id, "version": close_version},
            close_delay,
            task_id=self.build_vote_close_task_id(str(close_vote_id), close_version),
            ignore_already_exists=True,
        )
        self.logger.info(
            "Scheduled vote close",
            extra={"voteId": close_vote_id, "version": close_version, "delaySeconds": close_delay},
        )

        next_tick_version = request_version + 1
        delay_seconds = rotation.duration_ms / 1000
        enqueue_json_task_with_delay(
            self.settings.playback_queue,
            self._tick_url(),
            {"version": next_tick_version},
            delay_seconds,
            task_id=self.build_tick_task_id(rotation.vote_id, rotation.ends_at, next_tick_version),
            ignore_already_exists=True,
        )
        self.logger.info(
            "Scheduled next tick",
            extra={"voteId": rotation.vote_id, "delaySeconds": delay_seconds, "version": next_tick_version},
        )
