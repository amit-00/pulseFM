from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class TrackStatus(str, Enum):
    READY = "ready"
    PLAYING = "playing"
    ARCHIVED = "archived"
    FAILED = "failed"


class Track(BaseModel):
    id: UUID
    request_id: UUID
    audio_url: str
    duration_sec: int
    status: TrackStatus
    created_at: str
