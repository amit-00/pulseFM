import os
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "pulsefm_session")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7)))
    jwt_secret: str = os.getenv("SESSION_JWT_SECRET", "")
    vote_queue_name: str = os.getenv("VOTE_QUEUE_NAME", "tally-queue")
    tally_function_url: str = os.getenv("TALLY_FUNCTION_URL", os.getenv("TALLY_WORKER_URL", ""))
    firestore_vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")
    firestore_vote_windows_collection: str = os.getenv("VOTE_WINDOWS_COLLECTION", "voteWindows")
    firestore_votes_collection: str = os.getenv("VOTES_COLLECTION", "votes")

    def cookie_max_age(self) -> int:
        return self.session_ttl_seconds

    def cookie_expires_delta(self) -> timedelta:
        return timedelta(seconds=self.session_ttl_seconds)


settings = Settings()
