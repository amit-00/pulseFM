from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from google.cloud.firestore import AsyncClient

from app.models.request import RequestCreate, RequestOut, RequestStatus
from app.services.modal_worker import dispatch_to_modal_worker
from app.services.db import get_db

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/", response_model=RequestOut)
async def create_request(
    payload: RequestCreate,
    db: AsyncClient = Depends(get_db),
):

    new_request = {
        "request_id": str(uuid4()),
        "genre": payload.genre,
        "mood": payload.mood,
        "energy": payload.energy,
        "status": RequestStatus.QUEUED,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    doc_ref = db.collection("requests").document(document_id=new_request["request_id"])
    await doc_ref.set(new_request)

    try:
        await dispatch_to_modal_worker(
            request_id=new_request["request_id"],
            genre=new_request["genre"],
            mood=new_request["mood"],
            energy=new_request["energy"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return new_request
