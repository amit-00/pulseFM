import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from google.cloud.firestore import AsyncTransaction, async_transactional, Increment

from pulsefm_firestore.client import get_firestore_client

from pulsefm_tally_worker.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Tally Worker", version="1.0.0")


def _vote_doc_id(window_id: str, session_id: str) -> str:
    return f"{window_id}:{session_id}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@app.post("/task/vote")
async def tally_vote(request: Request) -> Dict[str, str]:
    payload = await request.json()
    window_id = payload.get("windowId")
    session_id = payload.get("sessionId")
    option = payload.get("option")

    if not window_id or not session_id or not option:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing fields")

    db = get_firestore_client()
    votes_ref = db.collection(settings.votes_collection)
    vote_state_ref = db.collection(settings.vote_state_collection).document("current")
    vote_window_ref = db.collection(settings.vote_windows_collection).document(window_id)

    state_snapshot = await vote_state_ref.get()
    if not state_snapshot.exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vote window not initialized")
    state = state_snapshot.to_dict() or {}
    if state.get("windowId") != window_id or state.get("status") != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vote window is not open")
    options = state.get("options") or []
    if option not in options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid option")

    vote_id = _vote_doc_id(window_id, session_id)

    @async_transactional
    async def _transaction_fn(transaction: AsyncTransaction):
        vote_doc = votes_ref.document(vote_id)
        snapshot = await vote_doc.get(transaction=transaction)
        now = _utc_now()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            if data.get("counted") is True:
                return False
            if data.get("option") and data.get("option") != option:
                raise ValueError("Vote option mismatch")
            transaction.update(vote_doc, {"counted": True, "countedAt": now})
        else:
            transaction.set(vote_doc, {
                "windowId": window_id,
                "sessionId": session_id,
                "option": option,
                "votedAt": now,
                "counted": True,
            })

        tally_field = f"tallies.{option}"
        transaction.update(vote_state_ref, {tally_field: Increment(1)})
        transaction.update(vote_window_ref, {tally_field: Increment(1)})
        return True

    transaction = db.transaction()
    try:
        applied = await _transaction_fn(transaction)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if not applied:
        logger.info("Duplicate vote ignored: %s", vote_id)
        return {"status": "duplicate"}

    return {"status": "ok"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy"}
