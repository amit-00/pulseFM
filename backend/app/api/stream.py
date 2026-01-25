import logging

from fastapi import APIRouter, HTTPException, Request

from app.models.request import ReadyRequest

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/now-playing")
async def get_now_playing(request: Request) -> dict[str, str | int]:
    station = request.app.state.station
    now_playing: ReadyRequest | None = station.get_now_playing()
    if not now_playing:
        raise HTTPException(status_code=404, detail="No track is currently playing")

    return {
        "request_id": now_playing.request_id,
        "duration_elapsed_ms": station.get_duration_elapsed_ms(),
        "duration_ms": now_playing.duration_ms,
    }
