import random
from datetime import datetime, timedelta, timezone

import pytest

from pulsefm_playback_service.logic import (
    CandidateSong,
    build_tick_task_id,
    build_vote_close_task_id,
    is_stale_version,
    pick_winner,
    plan_rotation,
    select_candidate,
)

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _station(version: int = 3) -> dict:
    return {
        "voteId": "old-song",
        "version": version,
        "next": {"voteId": "next-song", "durationMs": 90000},
    }


class TestVersionGate:
    def test_equal_version_is_stale(self) -> None:
        assert is_stale_version(request_version=3, current_version=3)

    def test_lower_version_is_stale(self) -> None:
        assert is_stale_version(request_version=2, current_version=3)

    def test_higher_version_proceeds(self) -> None:
        assert not is_stale_version(request_version=4, current_version=3)


class TestPickWinner:
    def test_clear_winner(self) -> None:
        assert pick_winner({"a": 5, "b": 2}) == "a"

    def test_tie_broken_deterministically_with_seeded_rng(self) -> None:
        assert pick_winner({"a": 3, "b": 3}, rng=random.Random(0)) in {"a", "b"}

    def test_empty_tallies(self) -> None:
        assert pick_winner({}) is None


class TestSelectCandidate:
    def test_skips_current_vote_id(self) -> None:
        songs = [("next-song", {"durationMs": 90000}), ("fresh", {"durationMs": 80000})]
        candidate = select_candidate(songs, current_vote_id="next-song")
        assert candidate == CandidateSong(song_id="fresh", duration_ms=80000, stubbed=False)

    def test_skips_missing_duration(self) -> None:
        songs = [("broken", {}), ("fresh", {"durationMs": 80000})]
        assert select_candidate(songs, None).song_id == "fresh"

    def test_no_candidates(self) -> None:
        assert select_candidate([], None) is None


class TestPlanRotation:
    def test_promotes_next_and_selects_candidate(self) -> None:
        plan = plan_rotation(
            _station(),
            candidate=CandidateSong("fresh", 80000, False),
            stubbed_duration_ms=None,
            request_version=4,
            now=NOW,
        )
        assert plan.vote_id == "next-song"
        assert plan.duration_ms == 90000
        assert plan.ends_at == NOW + timedelta(milliseconds=90000)
        assert plan.next_vote_id == "fresh"
        assert plan.next_stubbed is False
        assert plan.version == 4

    def test_falls_back_to_stubbed(self) -> None:
        plan = plan_rotation(
            _station(), candidate=None, stubbed_duration_ms=60000, request_version=4, now=NOW
        )
        assert plan.next_vote_id == "stubbed"
        assert plan.next_stubbed is True
        assert plan.next_duration_ms == 60000

    def test_missing_next_fields_raises(self) -> None:
        with pytest.raises(ValueError):
            plan_rotation(
                {"version": 3, "next": {}},
                candidate=None,
                stubbed_duration_ms=60000,
                request_version=4,
                now=NOW,
            )

    def test_no_candidate_and_no_stub_raises(self) -> None:
        with pytest.raises(ValueError):
            plan_rotation(_station(), candidate=None, stubbed_duration_ms=None, request_version=4, now=NOW)


class TestTaskIds:
    def test_tick_task_id_shape(self) -> None:
        ends = datetime(2026, 7, 15, 12, 1, 30, tzinfo=timezone.utc)
        assert build_tick_task_id("v1", ends, 4) == f"playback-v1-{int(ends.timestamp())}-4"

    def test_close_task_id_shape(self) -> None:
        assert build_vote_close_task_id("v1", 4) == "vote-close-v1-4"
