import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")
    vote_windows_collection: str = os.getenv("VOTE_WINDOWS_COLLECTION", "voteWindows")
    votes_collection: str = os.getenv("VOTES_COLLECTION", "votes")


settings = Settings()
