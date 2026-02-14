import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    stream_interval_ms: int = int(os.getenv("STREAM_INTERVAL_MS", "500"))
    tally_snapshot_interval_sec: int = int(os.getenv("TALLY_SNAPSHOT_INTERVAL_SEC", "10"))
    heartbeat_sec: int = int(os.getenv("HEARTBEAT_SEC", "15"))
    stations_collection: str = os.getenv("STATIONS_COLLECTION", "stations")
    vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")


settings = Settings()
