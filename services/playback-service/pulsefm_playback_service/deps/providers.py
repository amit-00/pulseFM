import logging

from fastapi import Depends
from google.cloud.firestore import AsyncClient

from pulsefm_playback_service.config import settings
from pulsefm_playback_service.integrations.events import EventPublisher
from pulsefm_playback_service.integrations.redis_state import RedisState
from pulsefm_playback_service.integrations.tasks import TaskScheduler
from pulsefm_playback_service.orchestrators.refresh_next_song_orchestrator import RefreshNextSongOrchestrator
from pulsefm_playback_service.orchestrators.startup_orchestrator import StartupOrchestrator
from pulsefm_playback_service.orchestrators.tick_orchestrator import TickOrchestrator
from pulsefm_playback_service.orchestrators.vote_close_orchestrator import VoteCloseOrchestrator
from pulsefm_playback_service.repositories.firestore_repository import FirestoreRepository

_db: AsyncClient | None = None


def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def get_firestore_client() -> AsyncClient:
    global _db
    if _db is None:
        _db = AsyncClient()
    return _db


def get_firestore_repository(
    db: AsyncClient = Depends(get_firestore_client),
    logger: logging.Logger = Depends(get_logger),
) -> FirestoreRepository:
    return FirestoreRepository(db=db, settings=settings, logger=logger)


def get_redis_state(
    logger: logging.Logger = Depends(get_logger),
) -> RedisState:
    return RedisState(logger=logger)


def get_event_publisher(
    logger: logging.Logger = Depends(get_logger),
) -> EventPublisher:
    return EventPublisher(settings=settings, logger=logger)


def get_task_scheduler(
    logger: logging.Logger = Depends(get_logger),
) -> TaskScheduler:
    return TaskScheduler(settings=settings, logger=logger)


def get_vote_close_orchestrator(
    repository: FirestoreRepository = Depends(get_firestore_repository),
    redis_state: RedisState = Depends(get_redis_state),
    events: EventPublisher = Depends(get_event_publisher),
    logger: logging.Logger = Depends(get_logger),
) -> VoteCloseOrchestrator:
    return VoteCloseOrchestrator(
        repository=repository,
        redis_state=redis_state,
        events=events,
        logger=logger,
    )


def get_tick_orchestrator(
    repository: FirestoreRepository = Depends(get_firestore_repository),
    redis_state: RedisState = Depends(get_redis_state),
    events: EventPublisher = Depends(get_event_publisher),
    tasks: TaskScheduler = Depends(get_task_scheduler),
    vote_close: VoteCloseOrchestrator = Depends(get_vote_close_orchestrator),
    logger: logging.Logger = Depends(get_logger),
) -> TickOrchestrator:
    return TickOrchestrator(
        repository=repository,
        redis_state=redis_state,
        events=events,
        tasks=tasks,
        vote_close=vote_close,
        logger=logger,
    )


def get_refresh_next_song_orchestrator(
    repository: FirestoreRepository = Depends(get_firestore_repository),
    redis_state: RedisState = Depends(get_redis_state),
    events: EventPublisher = Depends(get_event_publisher),
    logger: logging.Logger = Depends(get_logger),
) -> RefreshNextSongOrchestrator:
    return RefreshNextSongOrchestrator(
        repository=repository,
        redis_state=redis_state,
        events=events,
        logger=logger,
    )


def create_startup_orchestrator() -> StartupOrchestrator:
    logger = get_logger()
    repository = FirestoreRepository(db=get_firestore_client(), settings=settings, logger=logger)
    tasks = TaskScheduler(settings=settings, logger=logger)
    return StartupOrchestrator(repository=repository, tasks=tasks, logger=logger)
