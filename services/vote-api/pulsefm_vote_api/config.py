import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    vote_queue_name: str = os.getenv("VOTE_QUEUE_NAME", "tally-queue")
    tally_function_url: str = os.getenv("TALLY_FUNCTION_URL", os.getenv("TALLY_WORKER_URL", ""))
    vote_rl_sess_limit: int = int(os.getenv("VOTE_RL_SESS_LIMIT", "5"))
    vote_rl_sess_window: int = int(os.getenv("VOTE_RL_SESS_WINDOW", "10"))
    vote_rl_poll_limit: int = int(os.getenv("VOTE_RL_POLL_LIMIT", "1000"))
    vote_rl_poll_window: int = int(os.getenv("VOTE_RL_POLL_WINDOW", "10"))
    firestore_heartbeats_collection: str = os.getenv("HEARTBEATS_COLLECTION", "heartbeats")
    encoded_bucket: str = os.getenv("ENCODED_BUCKET", "pulsefm-generated-songs")
    encoded_prefix: str = os.getenv("ENCODED_PREFIX", "encoded/")


settings = Settings()
