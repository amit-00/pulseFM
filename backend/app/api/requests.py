from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends

from app.models.request import RequestCreate, RequestOut, RequestStatus
from app.storage import add_request_to_queue, get_request_queue
from app.services.queue import enqueue_request
from app.config import get_settings, Settings

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/", response_model=RequestOut)
async def create_request(
    payload: RequestCreate,
    settings: Settings = Depends(get_settings),
):

    new_request = {
        "id": str(uuid4()),
        "genre": payload.genre,
        "mood": payload.mood,
        "energy": payload.energy,
        "status": RequestStatus.QUEUED,
        "created_at": datetime.now().isoformat()
    }

    enqueue_request(
        project_id=settings.project_id,
        location=settings.location,
        queue_name=settings.queue_name,
        worker_url=settings.gen_worker_url,
        invoker_sa_email=settings.invoker_sa_email,
        payload=new_request,
    )

    return new_request


@router.get("/{request_id}")
async def get_request(request_id: UUID):
    queue = get_request_queue()
    for request in queue:
        if request["id"] == str(request_id):
            return request
    raise HTTPException(status_code=404, detail="Request not found")