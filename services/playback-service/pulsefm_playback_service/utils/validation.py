from typing import Any, Dict

from fastapi import HTTPException, status


def validate_tick_version(payload: Dict[str, Any]) -> int:
    version_raw = payload.get("version")
    if version_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version is required")
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be an integer")
    if version <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be positive")
    return version


def validate_vote_close_payload(payload: Dict[str, Any]) -> tuple[str, int]:
    vote_id = payload.get("voteId")
    version_raw = payload.get("version")
    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")
    if version_raw is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version is required")
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="version must be an integer")
    return vote_id, version
