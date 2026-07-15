"""Pure decision core for song rotation.

Extracted from main.py's _rotate_song transaction so version gating,
candidate selection, and stubbed fallback are unit-testable without
Firestore. Behavior mirrors the original inline logic exactly.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CandidateSong:
    song_id: str
    duration_ms: int
    stubbed: bool


@dataclass(frozen=True)
class RotationPlan:
    start_at: datetime
    ends_at: datetime
    duration_ms: int
    vote_id: str
    next_vote_id: str
    next_duration_ms: int
    next_stubbed: bool
    version: int


def is_stale_version(request_version: int, current_version: int) -> bool:
    return request_version <= current_version


def pick_winner(tallies: dict[str, int], rng: random.Random | None = None) -> str | None:
    if not tallies:
        return None
    choose = rng.choice if rng is not None else random.choice
    max_votes = max(tallies.values())
    tied = [option for option, count in tallies.items() if count == max_votes]
    return choose(tied) if tied else None


def select_candidate(
    ready_songs: list[tuple[str, dict]],
    current_vote_id: str | None,
) -> CandidateSong | None:
    for song_id, data in ready_songs:
        if current_vote_id and song_id == current_vote_id:
            continue
        duration_ms = data.get("durationMs")
        if duration_ms is None:
            continue
        return CandidateSong(song_id=song_id, duration_ms=int(duration_ms), stubbed=False)
    return None


def plan_rotation(
    station: dict,
    candidate: CandidateSong | None,
    stubbed_duration_ms: int | None,
    request_version: int,
    now: datetime,
) -> RotationPlan:
    next_data = station.get("next") or {}
    promoted_vote_id = next_data.get("voteId")
    promoted_duration = next_data.get("durationMs") or next_data.get("duration")
    if promoted_vote_id is None or promoted_duration is None:
        raise ValueError("stations/main.next is missing fields")

    if candidate is None:
        if stubbed_duration_ms is None:
            raise ValueError("No ready song or stubbed song")
        candidate = CandidateSong(song_id="stubbed", duration_ms=int(stubbed_duration_ms), stubbed=True)

    duration_ms = int(promoted_duration)
    return RotationPlan(
        start_at=now,
        ends_at=now + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        vote_id=str(promoted_vote_id),
        next_vote_id=candidate.song_id,
        next_duration_ms=candidate.duration_ms,
        next_stubbed=candidate.stubbed,
        version=request_version,
    )


def build_tick_task_id(vote_id: str | None, ends_at: datetime | None, version: int | None = None) -> str:
    suffix = vote_id or ""
    timestamp = str(int(ends_at.timestamp())) if ends_at else ""
    version_suffix = str(version) if version is not None else ""
    return f"playback-{suffix}-{timestamp}-{version_suffix}"


def build_vote_close_task_id(vote_id: str, version: int) -> str:
    return f"vote-close-{vote_id}-{version}"
