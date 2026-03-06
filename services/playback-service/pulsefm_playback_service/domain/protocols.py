from typing import Any, Protocol

from pulsefm_playback_service.domain.models import SongRotationResult


class FirestoreRepositoryProtocol(Protocol):
    async def get_station_state(self) -> dict[str, Any] | None: ...

    async def get_current_state(self) -> dict[str, Any] | None: ...

    async def set_current_state(self, state: dict[str, Any]) -> None: ...

    async def open_next_vote(self, version: int, duration_ms: int) -> dict[str, Any]: ...

    async def rotate_song(self, request_version: int) -> SongRotationResult | None: ...

    async def refresh_next_song(self, trigger_vote_id: str) -> dict[str, Any]: ...


class RedisStateProtocol(Protocol):
    async def open_poll_snapshot(
        self,
        vote_id: str,
        start_at: Any,
        end_at: Any,
        duration_ms: int,
        options: list[str],
        snapshot: dict[str, Any],
    ) -> None: ...

    async def set_poll_status(self, vote_id: str, status: str) -> None: ...

    async def get_poll_tallies(self, vote_id: str) -> dict[str, int]: ...

    async def reconcile_next_song_snapshot(self, result: dict[str, Any]) -> bool: ...


class EventPublisherProtocol(Protocol):
    def publish_vote_open(self, vote_id: str, end_at_ms: int | None) -> None: ...

    def publish_vote_close(self, vote_id: str, winner_option: str | None = None) -> None: ...

    def publish_changeover(self, rotation: SongRotationResult, request_version: int) -> None: ...

    def publish_next_song_changed(self, vote_id: str, duration_ms: int, version: int) -> None: ...


class TaskSchedulerProtocol(Protocol):
    @property
    def has_tick_url(self) -> bool: ...

    def schedule_startup_tick(self, station: dict[str, Any]) -> None: ...

    def schedule_next(self, rotation: SongRotationResult, window: dict[str, Any], request_version: int) -> None: ...


class VoteCloseOrchestratorProtocol(Protocol):
    async def close_current_vote_if_matches(
        self,
        expected_vote_id: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]: ...

    async def close_vote_state(self, state: dict[str, Any]) -> dict[str, Any]: ...
