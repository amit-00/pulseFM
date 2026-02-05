import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from pulsefm_pubsub.utils import decode_pubsub_push
from pulsefm_redis.client import get_redis_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Tally Service", version="1.0.0")

clients: set[asyncio.Queue] = set()


def _broadcast(message: Dict[str, Any]) -> None:
    for queue in list(clients):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            clients.discard(queue)


@app.get("/stream")
async def stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    clients.add(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        finally:
            clients.discard(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/pubsub/vote-events")
async def handle_vote_events(request: Request) -> Dict[str, str]:
    body = await request.json()
    payload, _ = decode_pubsub_push(body)

    window_id = payload.get("windowId")
    option = payload.get("option")
    if not window_id or not option:
        logger.warning("Invalid vote payload: %s", payload)
        return {"status": "ignored"}

    redis_client = get_redis_client()
    key = f"tally:{window_id}:{option}"
    count = redis_client.incr(key)

    _broadcast({"type": "tally", "windowId": window_id, "option": option, "count": count})
    return {"status": "ok"}


@app.post("/pubsub/window-changed")
async def handle_window_changed(request: Request) -> Dict[str, str]:
    body = await request.json()
    payload, _ = decode_pubsub_push(body)
    _broadcast({"type": "window", **payload})
    return {"status": "ok"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
