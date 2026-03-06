import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, status

from pulsefm_playback_service.deps import (
    create_startup_orchestrator,
    get_refresh_next_song_orchestrator,
    get_tick_orchestrator,
    get_vote_close_orchestrator,
)
from pulsefm_playback_service.orchestrators.refresh_next_song_orchestrator import RefreshNextSongOrchestrator
from pulsefm_playback_service.orchestrators.tick_orchestrator import TickOrchestrator
from pulsefm_playback_service.orchestrators.vote_close_orchestrator import VoteCloseOrchestrator
from pulsefm_playback_service.utils.validation import validate_vote_close_payload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(a: FastAPI):
    startup = create_startup_orchestrator()
    await startup.ensure_playback_tick_scheduled()
    yield


app = FastAPI(title="PulseFM Playback Service", version="1.0.0", lifespan=lifespan)


@app.post("/vote/close")
async def close_vote(
    payload: Dict[str, Any],
    orchestrator: VoteCloseOrchestrator = Depends(get_vote_close_orchestrator),
) -> Dict[str, Any]:
    vote_id, version = validate_vote_close_payload(payload)
    try:
        result = await orchestrator.close_current_vote_if_matches(expected_vote_id=vote_id, expected_version=version)
    except Exception:
        logger.exception("Failed to close vote", extra={"voteId": vote_id, "version": version})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to close vote")

    logger.info(
        "Close vote request handled",
        extra={"voteId": vote_id, "version": version, "action": result["action"]},
    )
    return {"status": "ok", **result}


@app.post("/next/refresh")
async def refresh_next_song(
    payload: Dict[str, Any],
    orchestrator: RefreshNextSongOrchestrator = Depends(get_refresh_next_song_orchestrator),
) -> Dict[str, Any]:
    return await orchestrator.run(payload)


@app.post("/tick")
async def tick(
    payload: Dict[str, Any],
    orchestrator: TickOrchestrator = Depends(get_tick_orchestrator),
) -> Dict[str, Any]:
    return await orchestrator.run(payload)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
