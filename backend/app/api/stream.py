import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.broadcaster import StreamBroadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])


async def stream_generator(broadcaster: StreamBroadcaster, subscriber_id: str, queue: asyncio.Queue):
    """
    Async generator that yields audio chunks from a subscriber queue.
    
    Args:
        broadcaster: StreamBroadcaster instance
        subscriber_id: ID of the subscriber
        queue: Subscriber's queue to read chunks from
    """
    try:
        while True:
            try:
                # Wait for chunk with timeout to allow periodic checks
                chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # None is a sentinel value indicating queue closure
                if chunk is None:
                    logger.info(f"Subscriber {subscriber_id} queue closed")
                    break
                
                yield chunk
                
            except asyncio.TimeoutError:
                # Timeout is normal, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error in stream generator for subscriber {subscriber_id}: {e}")
                break
    finally:
        # Unsubscribe when generator exits (client disconnected or error)
        await broadcaster.unsubscribe(subscriber_id)
        logger.info(f"Subscriber {subscriber_id} unsubscribed")


@router.get("/")
async def get_stream(request: Request):
    """
    Stream endpoint that subscribes a client and returns audio chunks.
    
    Returns a StreamingResponse with AAC ADTS audio chunks.
    """
    broadcaster: StreamBroadcaster = request.app.state.broadcaster
    
    if broadcaster is None:
        return {"error": "Broadcaster not available"}, 503
    
    # Subscribe and create stream generator
    subscriber_id, queue = await broadcaster.subscribe()
    
    return StreamingResponse(
        stream_generator(broadcaster, subscriber_id, queue),
        media_type="audio/aac",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )