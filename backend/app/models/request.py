from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Annotated
from pydantic import BaseModel, AfterValidator, ValidationError

class RequestStatus(str, Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    PLAYED = "played"
    FAILED = "failed"


class RequestGenre(str, Enum):
    POP = "pop"
    ROCK = "rock"
    HIP_HOP = "hip_hop"
    JAZZ = "jazz"
    CLASSICAL = "classical"
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