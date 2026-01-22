from fastapi import APIRouter

from app.models.request import RequestQueueOut
from app.core.scheduler import get_scheduler


router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/", response_model=RequestQueueOut)
async def get_queue():
    scheduler = get_scheduler()
    queue_state = await scheduler.get_queue_state()
    
    return RequestQueueOut(
        now_playing=queue_state.get("now_playing"),
        next_up=queue_state.get("next_up", [])
    )