import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import uuid

from fastapi import FastAPI
from google.cloud.firestore import AsyncClient

from pulsefm_descriptors.data import get_descriptor_keys
from pulsefm_firestore.client import get_firestore_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote Orchestrator", version="1.0.0")

VOTE_STATE_COLLECTION = os.getenv("VOTE_STATE_COLLECTION", "voteState")
VOTE_WINDOWS_COLLECTION = os.getenv("VOTE_WINDOWS_COLLECTION", "voteWindows")
WINDOW_SECONDS = int(os.getenv("WINDOW_SECONDS", "300"))
OPTIONS_PER_WINDOW = int(os.getenv("OPTIONS_PER_WINDOW", "4"))
VOTE_OPTIONS = [opt.strip() for opt in os.getenv("VOTE_OPTIONS", "").split(",") if opt.strip()]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_current_state(db: AsyncClient) -> Dict[str, Any] | None:
    doc = await db.collection(VOTE_STATE_COLLECTION).document("current").get()
    return doc.to_dict() if doc.exists else None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise ValueError("Invalid timestamp")


def _build_window(window_id: str, start_at: datetime, end_at: datetime, options: list[str], version: int) -> Dict[str, Any]:
    return {
        "windowId": window_id,
        "status": "OPEN",
        "startAt": start_at,
        "endAt": end_at,
        "options": options,
        "tallies": {option: 0 for option in options},
        "version": version,
        "createdAt": start_at,
    }


def _get_window_options() -> list[str]:
    if VOTE_OPTIONS:
        return VOTE_OPTIONS
    options = get_descriptor_keys()
    if len(options) < OPTIONS_PER_WINDOW:
        raise ValueError("Not enough descriptor options to sample window choices")
    return random.sample(options, OPTIONS_PER_WINDOW)


async def _close_window(db: AsyncClient, state: Dict[str, Any]) -> Dict[str, Any]:
    window_id = state.get("windowId")
    tallies = state.get("tallies") or {}

    winner_option = None
    if tallies:
        winner_option = max(tallies.items(), key=lambda item: item[1])[0]

    closed_at = _utc_now()

    window_doc = {
        **state,
        "status": "CLOSED",
        "winnerOption": winner_option,
        "tallies": tallies,
        "closedAt": closed_at,
    }

    await db.collection(VOTE_WINDOWS_COLLECTION).document(window_id).set(window_doc)
    await db.collection(VOTE_STATE_COLLECTION).document("current").set(window_doc)

    return window_doc


async def _open_next_window(db: AsyncClient, version: int) -> Dict[str, Any]:
    window_id = str(uuid.uuid4())
    start_at = _utc_now()
    end_at = start_at + timedelta(seconds=WINDOW_SECONDS)
    window_options = _get_window_options()

    window_doc = _build_window(window_id, start_at, end_at, window_options, version)
    await db.collection(VOTE_STATE_COLLECTION).document("current").set(window_doc)

    return window_doc


@app.post("/tick")
async def tick() -> Dict[str, Any]:
    db = get_firestore_client()
    state = await _get_current_state(db)

    if not state:
        window = await _open_next_window(db, 1)
        return {"status": "opened", "windowId": window["windowId"]}

    status = state.get("status")
    end_at = _parse_timestamp(state.get("endAt"))
    now = _utc_now()

    if status == "OPEN" and now >= end_at:
        await _close_window(db, state)
        window = await _open_next_window(db, int(state.get("version", 0)) + 1)
        return {"status": "rotated", "windowId": window["windowId"]}

    if status == "CLOSED":
        window = await _open_next_window(db, int(state.get("version", 0)) + 1)
        return {"status": "opened", "windowId": window["windowId"]}

    return {"status": "noop", "windowId": state.get("windowId")}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
