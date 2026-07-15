import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    stations_collection: str = os.getenv("STATIONS_COLLECTION", "stations")
    vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")


settings = Settings()
