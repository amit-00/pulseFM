from typing import List
from fastapi import APIRouter

from app.models.request import RequestOut
from app.storage import get_request_queue


router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/", response_model=List[RequestOut])
async def get_queue():
    queue = get_request_queue()
    return queue