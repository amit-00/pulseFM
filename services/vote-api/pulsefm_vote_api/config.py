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
    vote_rl_sess_limit: int = int(os.getenv("VOTE_RL_SESS_LIMIT", "5"))
    vote_rl_sess_window: int = int(os.getenv("VOTE_RL_SESS_WINDOW", "10"))
    vote_rl_poll_limit: int = int(os.getenv("VOTE_RL_POLL_LIMIT", "1000"))
    vote_rl_poll_window: int = int(os.getenv("VOTE_RL_POLL_WINDOW", "10"))
    session_rl_rate_per_min: int = int(os.getenv("SESSION_RL_RATE_PER_MIN", "100"))
    session_rl_burst: int = int(os.getenv("SESSION_RL_BURST", "500"))
    session_rl_rps: int = int(os.getenv("SESSION_RL_RPS", "25"))
    firestore_heartbeats_collection: str = os.getenv("HEARTBEATS_COLLECTION", "heartbeats")
    encoded_bucket: str = os.getenv("ENCODED_BUCKET", "pulsefm-generated-songs")
    encoded_prefix: str = os.getenv("ENCODED_PREFIX", "encoded/")

    def cookie_max_age(self) -> int:
        return self.session_ttl_seconds

    def cookie_expires_delta(self) -> timedelta:
        return timedelta(seconds=self.session_ttl_seconds)


settings = Settings()
