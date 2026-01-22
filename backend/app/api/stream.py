from fastapi import APIRouter, Depends
from google.cloud.firestore import AsyncClient
from fastapi.responses import StreamingResponse

from app.services.db import get_db

router = APIRouter(prefix="/stream", tags=["stream"])

@router.get("/")
async def get_stream(db: AsyncClient = Depends(get_db)):
    return {"message": "Stream is not implemented yet"}