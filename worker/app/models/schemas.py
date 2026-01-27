"""Pydantic models for API requests and responses."""
import uuid
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, AfterValidator


class GenerateRequest(BaseModel):
    """Request model for generate endpoint."""
    request_id: Annotated[
        str, 
        AfterValidator(lambda x: str(uuid.UUID(x)))
    ]


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
    CLASSICAL = "classical"
    ELECTRONIC = "electronic"
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


class GenRequest(BaseModel):
    request_id: Annotated[
        str, 
        AfterValidator(lambda x: str(uuid.UUID(x)))
    ]
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy
    status: RequestStatus
    created_at: str