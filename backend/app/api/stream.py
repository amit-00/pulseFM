import logging

from fastapi import APIRouter, HTTPException, Request
from google.cloud.exceptions import GoogleCloudError

from app.models.request import ReadyRequest
from app.services.storage import get_storage_blob

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/playing")
async def get_playing(request: Request) -> dict[str, str | int]:
    station = request.app.state.station
    now_playing: ReadyRequest | None = station.get_now_playing()
    if not now_playing:
        raise HTTPException(status_code=404, detail="No track is currently playing")

    audio_url = now_playing.audio_url
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
        
        return {
            "request_id": now_playing.request_id,
            "signed_url": signed_url,
            "duration_elapsed_ms": station.get_duration_elapsed_ms(),
            "duration_ms": now_playing.duration_ms,
            "stubbed": now_playing.stubbed,
        }
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleCloudError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")



@router.get("/next")
async def get_next(request: Request) -> dict[str, str | int]:
    station = request.app.state.station
    next_track: ReadyRequest | None = station.get_next_track()
    if not next_track:
        raise HTTPException(status_code=404, detail="No next track is available")

    audio_url = next_track.audio_url
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
        
        return {
            "request_id": next_track.request_id,
            "signed_url": signed_url,
            "duration_ms": next_track.duration_ms,
            "stubbed": next_track.stubbed,
        }
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleCloudError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")