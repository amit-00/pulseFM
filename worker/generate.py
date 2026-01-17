import uuid
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, AfterValidator
from google.cloud import firestore


db = firestore.AsyncClient()
app = FastAPI()


class GenerateRequest(BaseModel):
    request_id: Annotated[
        str, 
        AfterValidator(lambda x: str(uuid.uuid4()))
    ]


@app.post("/generate")
async def generate(payload: GenerateRequest):
    request_ref = db.collection("requests").document(payload.request_id)
    request = await request_ref.get()

    if not request.exists:
        raise HTTPException(status_code=404, detail="Request not found")

    request_ref.set({
        "status": "generating"
    })

    return Response(status_code=204)