import json

import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    get_playback_current_snapshot,
    playback_current_key,
    set_playback_current_snapshot,
    set_playback_poll_status,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "song-1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "song-2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 3, "status": "OPEN"},
    }


@pytest.mark.asyncio
async def test_close_writes_status_and_winner(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    await set_playback_poll_status(client, "v1", "CLOSED", winner_option="a")
    snapshot = await get_playback_current_snapshot(client)
    assert snapshot["poll"]["status"] == "CLOSED"
    assert snapshot["poll"]["winnerOption"] == "a"


@pytest.mark.asyncio
async def test_status_only_leaves_winner_absent(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    await set_playback_poll_status(client, "v1", "CLOSED")
    snapshot = await get_playback_current_snapshot(client)
    assert snapshot["poll"]["status"] == "CLOSED"
    assert "winnerOption" not in snapshot["poll"]


@pytest.mark.asyncio
async def test_vote_id_mismatch_raises(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    with pytest.raises(ValueError):
        await set_playback_poll_status(client, "other", "CLOSED", winner_option="a")
