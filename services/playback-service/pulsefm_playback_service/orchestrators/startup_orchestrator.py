import logging

from pulsefm_playback_service.domain.protocols import FirestoreRepositoryProtocol, TaskSchedulerProtocol


class StartupOrchestrator:
    def __init__(
        self,
        repository: FirestoreRepositoryProtocol,
        tasks: TaskSchedulerProtocol,
        logger: logging.Logger | None = None,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.logger = logger or logging.getLogger(__name__)

    async def ensure_playback_tick_scheduled(self) -> None:
        if not self.tasks.has_tick_url:
            self.logger.warning("PLAYBACK_TICK_URL not set; skipping startup scheduling")
            return

        station = await self.repository.get_station_state()
        if not station:
            self.logger.warning("stations/main missing; skipping startup scheduling")
            return

        self.tasks.schedule_startup_tick(station)
