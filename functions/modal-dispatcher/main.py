import asyncio
import logging
import os
from typing import Any, Dict

import functions_framework
import modal
from google.cloud.firestore import AsyncClient

from pulsefm_descriptors.data import DESCRIPTORS
from pulsefm_pubsub.client import decode_pubsub_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HEARTBEAT_COLLECTION = os.getenv("HEARTBEAT_COLLECTION", "heartbeat")

db = AsyncClient()


async def _get_active_listeners() -> int:
    doc = await db.collection(HEARTBEAT_COLLECTION).document("main").get()
    if not doc.exists:
        return 0
    data = doc.to_dict()
    return data.get("active_listeners", 0) if data else 0


async def _dispatch_modal_worker(vote_id: str, winner_option: str) -> None:
    descriptor = DESCRIPTORS.get(winner_option)
    if not descriptor:
        logger.warning("No descriptor found", extra={"winnerOption": winner_option})
        return

    genre = descriptor["genre"]
    mood = descriptor["mood"]
    energy = descriptor["energy"]

    logger.info(
        "Dispatching Modal worker",
        extra={
            "voteId": vote_id,
            "winnerOption": winner_option,
            "genre": genre,
            "mood": mood,
            "energy": energy,
        },
    )

    MusicGenerator = modal.Cls.from_name("pulsefm-worker", "MusicGenerator")
    generator = MusicGenerator()
    await generator.generate.spawn.aio(
        genre=genre,
        mood=mood,
        energy=energy,
        vote_id=vote_id,
    )


async def _handle(event) -> None:
    payload: Dict[str, Any] = decode_pubsub_json(event.data or {})
    event_type = payload.get("event")
    vote_id = payload.get("voteId")
    winner_option = payload.get("winnerOption")

    if event_type != "CLOSE":
        logger.info("Ignoring non-close event", extra={"event": event_type})
        return

    if not vote_id or not winner_option:
        logger.warning("Missing CLOSE payload fields", extra={"voteId": vote_id, "winnerOption": winner_option})
        return

    active_listeners = await _get_active_listeners()
    logger.info("Active listeners checked", extra={"voteId": vote_id, "count": active_listeners})
    if active_listeners < 1:
        logger.info("No active listeners, skipping dispatch", extra={"voteId": vote_id})
        return

    await _dispatch_modal_worker(vote_id, winner_option)


@functions_framework.cloud_event
def modal_dispatcher(event):
    asyncio.run(_handle(event))
