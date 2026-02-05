import os
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Settings:
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "pulsefm_session")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7)))
    jwt_secret: str = os.getenv("SESSION_JWT_SECRET", "")
    rate_limit_session_per_min: int = int(os.getenv("RL_SESSION_PER_MIN", "10"))
    rate_limit_ip_per_min: int = int(os.getenv("RL_IP_PER_MIN", "60"))
    vote_events_topic: str = os.getenv("VOTE_EVENTS_TOPIC", "vote-events")
    firestore_vote_state_collection: str = os.getenv("VOTE_STATE_COLLECTION", "voteState")
    firestore_vote_windows_collection: str = os.getenv("VOTE_WINDOWS_COLLECTION", "voteWindows")

    def cookie_max_age(self) -> int:
        return self.session_ttl_seconds

    def cookie_expires_delta(self) -> timedelta:
        return timedelta(seconds=self.session_ttl_seconds)


settings = Settings()
