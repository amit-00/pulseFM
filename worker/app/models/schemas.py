"""Pydantic models for API requests and responses."""
import uuid
from typing import Annotated
from pydantic import BaseModel, AfterValidator


class GenerateRequest(BaseModel):
    """Request model for generate endpoint."""
    request_id: Annotated[
        str, 
        AfterValidator(lambda x: str(uuid.UUID(x)))
    ]

