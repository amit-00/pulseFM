import logging
from typing import Any

from pulsefm_pubsub.client import publish_json

from pulsefm_playback_service.config import Settings
from pulsefm_playback_service.domain.models import SongRotationResult


class EventPublisher:
    def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    def publish_vote_open(self, vote_id: str, end_at_ms: int | None) -> None:
        payload: dict[str, Any] = {"event": "OPEN", "voteId": vote_id}
        if end_at_ms is not None:
            payload["endAt"] = end_at_ms
        publish_json(self.settings.project_id or None, self.settings.vote_events_topic, payload)

    def publish_vote_close(self, vote_id: str, winner_option: str | None = None) -> None:
        payload: dict[str, Any] = {"event": "CLOSE", "voteId": vote_id}
        if winner_option is not None:
            payload["winnerOption"] = winner_option
        publish_json(self.settings.project_id or None, self.settings.vote_events_topic, payload)

    def publish_playback_event(self, event: str, payload: dict[str, Any]) -> None:
        event_payload = {"event": event, **payload}
        publish_json(self.settings.project_id or None, self.settings.playback_events_topic, event_payload)

    def publish_changeover(self, rotation: SongRotationResult, request_version: int) -> None:
        self.publish_playback_event(
            "NEXT-SONG-CHANGED",
            {
                "voteId": rotation.next_vote_id,
                "durationMs": rotation.next_duration_ms,
                "version": request_version,
            },
        )
        self.publish_playback_event("CHANGEOVER", {"durationMs": rotation.duration_ms, "version": request_version})

    def publish_next_song_changed(self, vote_id: str, duration_ms: int, version: int) -> None:
        self.publish_playback_event(
            "NEXT-SONG-CHANGED",
            {"voteId": vote_id, "durationMs": duration_ms, "version": version},
        )
