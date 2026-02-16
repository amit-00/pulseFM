import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    vote_queue_name: str = os.getenv("VOTE_QUEUE_NAME", "tally-queue")
    tally_function_url: str = os.getenv("TALLY_FUNCTION_URL", os.getenv("TALLY_WORKER_URL", ""))
    encoded_bucket: str = os.getenv("ENCODED_BUCKET", "pulsefm-generated-songs")
    encoded_prefix: str = os.getenv("ENCODED_PREFIX", "encoded/")


settings = Settings()
