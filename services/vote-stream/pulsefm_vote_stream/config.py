import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "pulsefm_session")
    jwt_secret: str = os.getenv("SESSION_JWT_SECRET", "")
    stream_interval_ms: int = int(os.getenv("STREAM_INTERVAL_MS", "500"))


settings = Settings()
