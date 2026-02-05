from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Annotated, List
from pydantic import BaseModel, AfterValidator, ValidationError

class RequestStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    PLAYING = "playing"
    PLAYED = "played"
    FAILED = "failed"


class RequestGenre(str, Enum):
    POP = "pop"
    ROCK = "rock"
    HIP_HOP = "hip_hop"
    JAZZ = "jazz"
    ELECTRONIC = "electronic"
    LOFI = "lofi"
    RNB = "rnb"


class RequestMood(str, Enum):
    HAPPY = "happy"
    SAD = "sad"
    CALM = "calm"
    EXCITING = "exciting"
    ROMANTIC = "romantic"
    PARTY = "party"


class RequestEnergy(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"


class RequestCreate(BaseModel):
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy = RequestEnergy.MID


class RequestQueueOut(BaseModel):
    now_playing: str
    next_up: List[str]


class ReadyRequest(BaseModel):
    request_id: str
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy
    status: RequestStatus
    created_at: str
    audio_url: str
    duration_ms: int
    stubbed: bool = False


def validate_uuid(v: str) -> UUID:
    try:
        return str(UUID(v))
    except ValueError:
        raise ValidationError("Invalid UUID")


class RequestOut(BaseModel):
    request_id: Annotated[str, AfterValidator(validate_uuid)]
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy
    status: RequestStatus
    created_at: str