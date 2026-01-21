from fastapi import APIRouter

from app.models.request import RequestQueueOut
from app.storage import get_request_queue


router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/", response_model=RequestQueueOut)
async def get_queue():
    queue = get_request_queue()
    
    if not queue:
        return RequestQueueOut(now_playing=None, next_up=[])

    return {
        "now_playing": queue[0]["id"],
        "next_up": [request["id"] for request in queue[1:]]
    }