from google.cloud.firestore import AsyncClient
from fastapi import APIRouter, Depends, HTTPException
from google.cloud.exceptions import GoogleCloudError

from app.services.db import get_db
from app.services.storage import get_storage_blob


router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("/{request_id}")
async def get_track(
    request_id: str, 
    db: AsyncClient = Depends(get_db),
):
    doc_ref = None
    if request_id.startswith("stub-"):
        doc_ref = db.collection("stubbed").document(document_id=request_id.replace("stub-", ""))
    else:
        doc_ref = db.collection("requests").document(document_id=request_id)

    doc = await doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Track not found")

    data = doc.to_dict()
    audio_url = data.get("audio_url")
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio URL not found")

    try:
        blob = get_storage_blob(audio_url)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Audio file not found in storage")
        
        # Generate signed URL with 1 hour expiration
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=3600,  # 1 hour
            method="GET"
        )
        
        return {"url": signed_url}
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleCloudError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")