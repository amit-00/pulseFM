from typing import List
from pydantic import BaseModel

class QueueOut(BaseModel):
    now_playing: str
    next_up: List[str]