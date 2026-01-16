from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel

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
    MEDIUM = "medium"
    HIGH = "high"


class RequestCreate(BaseModel):
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy = RequestEnergy.MEDIUM


class RequestOut(BaseModel):
    id: UUID
    genre: RequestGenre
    mood: RequestMood
    energy: RequestEnergy
    status: RequestStatus
    created_at: str