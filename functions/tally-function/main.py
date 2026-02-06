import os
from typing import Any, Dict

import functions_framework
from google.cloud.firestore import AsyncClient, AsyncTransaction, async_transactional, SERVER_TIMESTAMP, Increment

VOTE_STATE_COLLECTION = os.getenv("VOTE_STATE_COLLECTION", "voteState")
VOTES_COLLECTION = os.getenv("VOTES_COLLECTION", "votes")

db = AsyncClient()


def _vote_doc_id(vote_id: str, session_id: str) -> str:
    return f"{vote_id}:{session_id}"


def _success(status: str, extra: Dict[str, Any] | None = None, code: int = 200):
    payload = {"status": status}
    if extra:
        payload.update(extra)
    return payload, code


@functions_framework.http
async def tally_function(request):
    if request.method != "POST":
        return _success("method_not_allowed", code=405)

    payload = request.get_json(silent=True) or {}
    vote_id = payload.get("voteId")
    session_id = payload.get("sessionId")
    option = payload.get("option")

    if not vote_id or not session_id or not option:
        return _success("missing_fields")

    vote_state_ref = db.collection(VOTE_STATE_COLLECTION).document("current")
    votes_ref = db.collection(VOTES_COLLECTION)
    vote_doc_id = _vote_doc_id(vote_id, session_id)

    @async_transactional
    async def _transaction_fn(transaction: AsyncTransaction) -> str:
        state_snapshot = await vote_state_ref.get(transaction=transaction)
        if not state_snapshot.exists:
            return "vote_not_initialized"
        state = state_snapshot.to_dict() or {}
        if state.get("voteId") != vote_id or state.get("status") != "OPEN":
            return "vote_not_open"
        options = state.get("options") or []
        if option not in options:
            return "invalid_option"

        vote_doc_ref = votes_ref.document(vote_doc_id)
        vote_snapshot = await vote_doc_ref.get(transaction=transaction)
        if not vote_snapshot.exists:
            return "vote_missing"
        vote_data = vote_snapshot.to_dict() or {}
        if vote_data.get("counted") is True:
            return "duplicate"
        if vote_data.get("option") and vote_data.get("option") != option:
            return "option_mismatch"

        transaction.update(vote_doc_ref, {
            "counted": True,
            "countedAt": SERVER_TIMESTAMP,
        })
        transaction.update(vote_state_ref, {f"tallies.{option}": Increment(1)})
        return "ok"

    transaction = db.transaction()
    try:
        result = await _transaction_fn(transaction)
    except Exception:
        return _success("error", code=500)

    return _success(result)
