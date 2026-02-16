import base64
import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Mapping

import functions_framework
import modal
from google.cloud.firestore import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HEARTBEAT_COLLECTION = os.getenv("HEARTBEAT_COLLECTION", "heartbeat")

DESCRIPTORS = {
    "alluring": {"mood": "romantic", "genre": "rnb", "energy": "mid"},
    "ambient": {"mood": "happy", "genre": "electronic", "energy": "low"},
    "anticipatory": {"mood": "exciting", "genre": "pop", "energy": "low"},
    "ardent": {"mood": "romantic", "genre": "jazz", "energy": "high"},
    "atmospheric": {"mood": "sad", "genre": "electronic", "energy": "mid"},
    "bittersweet": {"mood": "sad", "genre": "pop", "energy": "mid"},
    "bluesy": {"mood": "sad", "genre": "jazz", "energy": "mid"},
    "boisterous": {"mood": "party", "genre": "jazz", "energy": "high"},
    "bouncy": {"mood": "party", "genre": "hip_hop", "energy": "low"},
    "brooding": {"mood": "sad", "genre": "rock", "energy": "mid"},
    "bubbly": {"mood": "happy", "genre": "pop", "energy": "high"},
    "building": {"mood": "exciting", "genre": "rock", "energy": "low"},
    "buoyant": {"mood": "calm", "genre": "pop", "energy": "high"},
    "burning": {"mood": "romantic", "genre": "rnb", "energy": "high"},
    "cathartic": {"mood": "sad", "genre": "pop", "energy": "high"},
    "celebratory": {"mood": "party", "genre": "pop", "energy": "high"},
    "chill": {"mood": "happy", "genre": "hip_hop", "energy": "low"},
    "cozy": {"mood": "romantic", "genre": "rock", "energy": "mid"},
    "devoted": {"mood": "romantic", "genre": "pop", "energy": "high"},
    "dramatic": {"mood": "sad", "genre": "electronic", "energy": "high"},
    "dreamy": {"mood": "happy", "genre": "pop", "energy": "low"},
    "driving": {"mood": "exciting", "genre": "rock", "energy": "mid"},
    "dynamic": {"mood": "exciting", "genre": "pop", "energy": "mid"},
    "ecstatic": {"mood": "happy", "genre": "electronic", "energy": "high"},
    "effortless": {"mood": "calm", "genre": "jazz", "energy": "high"},
    "electrifying": {"mood": "exciting", "genre": "pop", "energy": "high"},
    "emotional": {"mood": "sad", "genre": "rnb", "energy": "mid"},
    "enchanting": {"mood": "romantic", "genre": "electronic", "energy": "mid"},
    "energetic": {"mood": "happy", "genre": "rock", "energy": "high"},
    "ethereal": {"mood": "sad", "genre": "electronic", "energy": "low"},
    "euphoric": {"mood": "happy", "genre": "electronic", "energy": "mid"},
    "explosive": {"mood": "exciting", "genre": "rock", "energy": "high"},
    "exuberant": {"mood": "happy", "genre": "rnb", "energy": "high"},
    "fervent": {"mood": "romantic", "genre": "rock", "energy": "high"},
    "festive": {"mood": "party", "genre": "pop", "energy": "mid"},
    "fierce": {"mood": "exciting", "genre": "hip_hop", "energy": "high"},
    "fiery": {"mood": "exciting", "genre": "jazz", "energy": "high"},
    "floating": {"mood": "calm", "genre": "electronic", "energy": "low"},
    "flowing": {"mood": "calm", "genre": "rock", "energy": "high"},
    "fluid": {"mood": "calm", "genre": "rnb", "energy": "high"},
    "frenetic": {"mood": "party", "genre": "rnb", "energy": "high"},
    "funky": {"mood": "party", "genre": "rock", "energy": "low"},
    "gentle": {"mood": "happy", "genre": "rock", "energy": "low"},
    "groovy": {"mood": "happy", "genre": "hip_hop", "energy": "mid"},
    "hypnotic": {"mood": "calm", "genre": "electronic", "energy": "mid"},
    "infectious": {"mood": "party", "genre": "hip_hop", "energy": "mid"},
    "intense": {"mood": "sad", "genre": "rock", "energy": "high"},
    "intimate": {"mood": "romantic", "genre": "rock", "energy": "low"},
    "introspective": {"mood": "sad", "genre": "hip_hop", "energy": "low"},
    "jazzy": {"mood": "happy", "genre": "jazz", "energy": "high"},
    "laidback": {"mood": "calm", "genre": "jazz", "energy": "mid"},
    "lively": {"mood": "party", "genre": "jazz", "energy": "mid"},
    "lush": {"mood": "romantic", "genre": "jazz", "energy": "mid"},
    "meditative": {"mood": "calm", "genre": "jazz", "energy": "low"},
    "melancholic": {"mood": "sad", "genre": "pop", "energy": "low"},
    "mellow": {"mood": "happy", "genre": "rnb", "energy": "low"},
    "mournful": {"mood": "sad", "genre": "jazz", "energy": "low"},
    "mystical": {"mood": "romantic", "genre": "electronic", "energy": "low"},
    "nostalgic": {"mood": "romantic", "genre": "jazz", "energy": "low"},
    "overwhelming": {"mood": "exciting", "genre": "electronic", "energy": "high"},
    "passionate": {"mood": "sad", "genre": "jazz", "energy": "high"},
    "peaceful": {"mood": "calm", "genre": "pop", "energy": "mid"},
    "playful": {"mood": "party", "genre": "pop", "energy": "low"},
    "powerful": {"mood": "sad", "genre": "rnb", "energy": "high"},
    "pulsing": {"mood": "calm", "genre": "electronic", "energy": "high"},
    "pumping": {"mood": "exciting", "genre": "hip_hop", "energy": "mid"},
    "raucous": {"mood": "party", "genre": "electronic", "energy": "mid"},
    "raving": {"mood": "party", "genre": "electronic", "energy": "high"},
    "raw": {"mood": "sad", "genre": "hip_hop", "energy": "high"},
    "reflective": {"mood": "sad", "genre": "hip_hop", "energy": "mid"},
    "relaxed": {"mood": "calm", "genre": "hip_hop", "energy": "mid"},
    "rising": {"mood": "exciting", "genre": "electronic", "energy": "low"},
    "rowdy": {"mood": "party", "genre": "rock", "energy": "mid"},
    "scorching": {"mood": "exciting", "genre": "rnb", "energy": "high"},
    "seductive": {"mood": "romantic", "genre": "hip_hop", "energy": "high"},
    "sensual": {"mood": "romantic", "genre": "hip_hop", "energy": "low"},
    "serene": {"mood": "calm", "genre": "pop", "energy": "low"},
    "silky": {"mood": "romantic", "genre": "hip_hop", "energy": "mid"},
    "sizzling": {"mood": "exciting", "genre": "rnb", "energy": "mid"},
    "slick": {"mood": "party", "genre": "rnb", "energy": "low"},
    "smooth": {"mood": "happy", "genre": "jazz", "energy": "low"},
    "soft": {"mood": "calm", "genre": "rnb", "energy": "low"},
    "somber": {"mood": "sad", "genre": "rock", "energy": "low"},
    "soothing": {"mood": "calm", "genre": "rock", "energy": "mid"},
    "soulful": {"mood": "happy", "genre": "rnb", "energy": "mid"},
    "spirited": {"mood": "party", "genre": "rnb", "energy": "mid"},
    "steady": {"mood": "calm", "genre": "hip_hop", "energy": "high"},
    "sultry": {"mood": "exciting", "genre": "rnb", "energy": "low"},
    "sunny": {"mood": "happy", "genre": "pop", "energy": "mid"},
    "swanky": {"mood": "party", "genre": "jazz", "energy": "low"},
    "sweet": {"mood": "romantic", "genre": "pop", "energy": "mid"},
    "swelling": {"mood": "exciting", "genre": "jazz", "energy": "low"},
    "swinging": {"mood": "happy", "genre": "jazz", "energy": "mid"},
    "syncopated": {"mood": "exciting", "genre": "jazz", "energy": "mid"},
    "tender": {"mood": "romantic", "genre": "pop", "energy": "low"},
    "thrilling": {"mood": "exciting", "genre": "electronic", "energy": "mid"},
    "throbbing": {"mood": "exciting", "genre": "hip_hop", "energy": "low"},
    "thumping": {"mood": "party", "genre": "electronic", "energy": "low"},
    "tranquil": {"mood": "calm", "genre": "rock", "energy": "low"},
    "transcendent": {"mood": "romantic", "genre": "electronic", "energy": "high"},
    "turnt": {"mood": "party", "genre": "hip_hop", "energy": "high"},
    "uplifting": {"mood": "happy", "genre": "rock", "energy": "mid"},
    "velvety": {"mood": "romantic", "genre": "rnb", "energy": "low"},
    "vibrant": {"mood": "happy", "genre": "hip_hop", "energy": "high"},
    "warm": {"mood": "calm", "genre": "rnb", "energy": "mid"},
    "wild": {"mood": "party", "genre": "rock", "energy": "high"},
    "wistful": {"mood": "sad", "genre": "rnb", "energy": "low"},
    "zen": {"mood": "calm", "genre": "hip_hop", "energy": "low"},
}


@lru_cache(maxsize=1)
def _get_firestore_client() -> Client:
    return Client()


def _decode_pubsub_json(payload: Mapping[str, Any]) -> dict[str, Any]:
    message = payload.get("message") or {}
    data = message.get("data")
    if not data:
        return {}
    try:
        raw = base64.b64decode(data)
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        decoded = json.loads(data)
    if isinstance(decoded, dict):
        return decoded
    return {"data": decoded}


def _get_active_listeners() -> int:
    db = _get_firestore_client()
    doc = db.collection(HEARTBEAT_COLLECTION).document("main").get()
    if not doc.exists:
        return 0
    data = doc.to_dict()
    if not data:
        return 0
    return int(data.get("activeListeners", data.get("active_listeners", 0)) or 0)


def _dispatch_modal_worker(vote_id: str, winner_option: str) -> None:
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
    generator.generate.spawn(
        genre=genre,
        mood=mood,
        energy=energy,
        vote_id=vote_id,
    )


def _handle(event) -> None:
    payload: Dict[str, Any] = _decode_pubsub_json(event.data or {})
    event_type = payload.get("event")
    vote_id = payload.get("voteId")
    winner_option = payload.get("winnerOption")

    if event_type != "CLOSE":
        logger.info("Ignoring non-close event", extra={"event": event_type})
        return

    if not vote_id or not winner_option:
        logger.warning("Missing CLOSE payload fields", extra={"voteId": vote_id, "winnerOption": winner_option})
        return

    active_listeners = _get_active_listeners()
    logger.info("Active listeners checked", extra={"voteId": vote_id, "count": active_listeners})
    if active_listeners < 1:
        logger.info("No active listeners, skipping dispatch", extra={"voteId": vote_id})
        return

    _dispatch_modal_worker(vote_id, winner_option)


@functions_framework.cloud_event
def modal_dispatcher(event):
    _handle(event)
