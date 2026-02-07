import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    stations_collection: str = os.getenv("STATIONS_COLLECTION", "stations")
    songs_collection: str = os.getenv("SONGS_COLLECTION", "songs")
    vote_orchestrator_queue: str = os.getenv("VOTE_ORCHESTRATOR_QUEUE", "vote-orchestrator-queue")
    vote_orchestrator_url: str = os.getenv("VOTE_ORCHESTRATOR_URL", "")


settings = Settings()
