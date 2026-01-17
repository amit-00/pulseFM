from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from google.cloud.firestore import AsyncClient


from app.models.request import RequestCreate, RequestOut, RequestStatus
from app.storage import get_request_queue
from app.services.queue import enqueue_request
from app.config import get_settings, Settings
from app.services.db import get_db

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/", response_model=RequestOut)
async def create_request(
    payload: RequestCreate,
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_db),
):

    new_request = {
        "request_id": str(uuid4()),
        "genre": payload.genre,
        "mood": payload.mood,
        "energy": payload.energy,
        "status": RequestStatus.QUEUED,
        "created_at": datetime.now().isoformat()
    }

    doc_ref = db.collection("requests").document(document_id=new_request["request_id"])
    await doc_ref.set(new_request)

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