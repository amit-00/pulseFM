"""Firestore service."""
import logging
from google.cloud import firestore
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def fail_request(request_ref: firestore.DocumentReference, error: str):
    """Mark a request as failed in Firestore."""
    logger.error(f"Failing request {request_ref.id}: {error}")
    try:
        await request_ref.set({
            "status": "failed"
        }, merge=True)
        logger.info(f"Updated request {request_ref.id} status to 'failed'")
    except Exception as e:
        logger.error(f"Failed to update request status in Firestore: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=error)

