import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    init_poll_open_atomic,
    set_playback_current_snapshot,
    submit_vote_atomic,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str, status: str = "OPEN") -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": status},
    }


async def _open_poll(client: FakeAsyncRedis, vote_id: str = "v1") -> None:
    await init_poll_open_atomic(client, vote_id, _snapshot(vote_id), 3600, 3600, ["a", "b"])


async def test_first_vote_counts(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "ok"
    assert await client.hget("pulsefm:poll:v1:tally", "a") == "1"


async def test_duplicate_session_rejected_and_not_double_counted(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    await submit_vote_atomic(client, "v1", "sess-1", "a")
    assert await submit_vote_atomic(client, "v1", "sess-1", "b") == "duplicate"
    assert await client.hget("pulsefm:poll:v1:tally", "a") == "1"
    assert await client.hget("pulsefm:poll:v1:tally", "b") == "0"


async def test_closed_poll_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    await set_playback_current_snapshot(client, _snapshot("v1", status="CLOSED"), 3600)
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "closed"


async def test_stale_vote_id_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client, "v2")
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "not_current"


async def test_unknown_option_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    assert await submit_vote_atomic(client, "v1", "sess-1", "zzz") == "invalid_option"


async def test_missing_snapshot_reports_no_state(client: FakeAsyncRedis) -> None:
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "no_state"
