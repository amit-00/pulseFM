from dataclasses import dataclass
from datetime import datetime


@dataclass
class SongRotationResult:
    start_at: datetime
    ends_at: datetime
    duration_ms: int
    vote_id: str
    next_vote_id: str
    next_duration_ms: int
    next_stubbed: bool
    version: int
