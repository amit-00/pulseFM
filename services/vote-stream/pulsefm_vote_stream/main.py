import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from fastapi import Cookie, FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from pulsefm_auth.session import verify_session_token
from pulsefm_redis.client import get_redis_client, poll_state_key, poll_tally_key

from pulsefm_vote_stream.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote Stream", version="1.0.0")


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\n" f"data: {payload}\n\n"


async def _fetch_snapshot(redis_client) -> Dict[str, Any]:
    vote_id = await redis_client.get("pulsefm:poll:current")  # type: ignore[misc]
    if not vote_id:
        return {
            "voteId": None,
            "status": None,
            "opensAt": None,
            "closesAt": None,
            "tallies": {},
            "ts": _utc_ms(),
        }

    state = await redis_client.hgetall(poll_state_key(vote_id))  # type: ignore[misc]
    tallies_raw = await redis_client.hgetall(poll_tally_key(vote_id))  # type: ignore[misc]
    tallies: Dict[str, int] = {}
    for option, value in tallies_raw.items():
        try:
            tallies[option] = int(value)
        except (TypeError, ValueError):
            tallies[option] = 0

    return {
        "voteId": vote_id,
        "status": state.get("status"),
        "opensAt": _to_int_or_none(state.get("opensAt")),
        "closesAt": _to_int_or_none(state.get("closesAt")),
        "tallies": tallies,
        "ts": _utc_ms(),
    }


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compute_events(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> list[Tuple[str, Dict[str, Any]]]:
    if previous is None:
        return [("poll", current)]

    poll_changed = (
        previous.get("voteId") != current.get("voteId")
        or previous.get("status") != current.get("status")
        or previous.get("opensAt") != current.get("opensAt")
        or previous.get("closesAt") != current.get("closesAt")
    )
    if poll_changed:
        return [("poll", current)]

    previous_tallies = previous.get("tallies") or {}
    current_tallies = current.get("tallies") or {}
    changes: Dict[str, int] = {}
    for option, value in current_tallies.items():
        if previous_tallies.get(option) != value:
            changes[option] = value

    if changes:
        return [("tally", {"voteId": current.get("voteId"), "changes": changes, "ts": current.get("ts")})]
    return []


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    try:
        redis_client = get_redis_client()
    except Exception:
        logger.exception("Redis unavailable for stream")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Redis unavailable")

    interval = max(50, settings.stream_interval_ms)
    last_snapshot: Optional[Dict[str, Any]] = None

    while True:
        if await request.is_disconnected():
            logger.info("Client disconnected from stream")
            break

        try:
            snapshot = await _fetch_snapshot(redis_client)
        except Exception:
            logger.exception("Redis read failed during stream")
            break

        for event, data in _compute_events(last_snapshot, snapshot):
            yield _format_sse(event, data)
        last_snapshot = snapshot

        try:
            await asyncio.sleep(interval / 1000)
        except asyncio.CancelledError:
            break


@app.get("/stream")
async def stream_votes(
    request: Request,
    session_cookie: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name),
):
    if not session_cookie:
        logger.warning("Missing session cookie")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session cookie")

    try:
        claims = verify_session_token(session_cookie, settings.jwt_secret)
    except Exception:
        logger.warning("Invalid session cookie")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session cookie")

    session_id = claims.get("sid")
    if not session_id:
        logger.warning("Session cookie missing sid claim")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session cookie")

    logger.info("Stream connected", extra={"sessionId": session_id})
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_event_stream(request), headers=headers)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
