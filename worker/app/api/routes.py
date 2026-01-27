"""API routes."""
import logging
from fastapi import APIRouter, HTTPException, Response

from google.cloud import firestore
from google.cloud.storage import Bucket

from app.models.schemas import GenerateRequest
from app.config.settings import STUBS_FOLDER
from app.services.storage import init_bucket
from app.services.firestore import fail_request
from app.services.processing import download_encode_and_upload

logger = logging.getLogger(__name__)

# Initialize bucket and database
bucket: Bucket = init_bucket()
db: firestore.AsyncClient = firestore.AsyncClient()

router = APIRouter()


@router.post("/generate")
async def generate(payload: GenerateRequest):
    """Generate audio file from request."""
    request_id = payload.request_id
    logger.info(f"Received generate request for request_id: {request_id}")
    
    request_ref = db.collection("requests").document(request_id)
    logger.debug(f"Fetching request document: {request_id}")
    request = await request_ref.get()
    
    if not request.exists:
        logger.warning(f"Request not found: {request_id}")
        raise HTTPException(status_code=404, detail="Request not found")

    logger.info(f"Updating request {request_id} status to 'generating'")
    await request_ref.set({
        "status": "generating"
    }, merge=True)

    audio_url = None

    try:
        request_data = request.to_dict()
        logger.debug(f"Request data: {request_data}")
        
        # Download asset, encode to .m4a, and upload to GCS
        # Uses temp files with automatic cleanup
        source_object_name = f"{STUBS_FOLDER}/{request_data['energy']}.wav"
        audio_url, duration_ms = await download_encode_and_upload(
            bucket,
            source_object_name,
            f"{request_id}.m4a"
        )
            
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {e}", exc_info=True)
        await fail_request(request_ref, str(e))

    if audio_url is None:
        logger.error(f"Output URL is None for request {request_id}")
        await fail_request(request_ref, "Failed to generate music")

    # Successful generation
    try:
        await request_ref.set({
            "status": "ready",
            "audio_url": audio_url,
            "duration_ms": duration_ms
        }, merge=True)
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
        await fail_request(request_ref, "Failed to update request status in Firestore")

    logger.info(f"Successfully completed generate request for {request_id}")
    return Response(status_code=204)

