import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")
    votes_collection: str = os.getenv("VOTES_COLLECTION", "votes")


settings = Settings()
