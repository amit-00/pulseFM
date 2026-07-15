import json

import pytest
from fakeredis import FakeAsyncRedis

import pulsefm_playback_stream.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_state_serves_winner_from_snapshot(
    monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis
) -> None:
    snapshot = {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 9999999999999, "durationMs": 100000},
        "nextSong": {"voteId": "s2", "durationMs": 100000},
        "poll": {"voteId": "v1", "options": ["a", "b"], "version": 5, "status": "CLOSED", "winnerOption": "b"},
    }
    await redis_client.set("pulsefm:playback:current", json.dumps(snapshot))
    await redis_client.hset("pulsefm:poll:v1:tally", mapping={"a": 2, "b": 7})

    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    # /state only touches Firestore when the Redis snapshot is missing.
    monkeypatch.setattr(main, "get_firestore_client", lambda: object())
    main.app.state.stream = main.StreamState()

    body = await main.get_state()

    assert body["poll"]["winnerOption"] == "b"
    assert body["poll"]["tallies"] == {"a": 2, "b": 7}
    assert body["redisAvailable"] is True


def test_sse_surface_removed() -> None:
    paths = {route.path for route in main.app.routes}
    assert "/stream" not in paths
    assert not any(p.startswith("/events/") for p in paths)
    assert "/state" in paths and "/health" in paths


def test_stream_state_has_no_event_markers() -> None:
    state = main.StreamState()
    for legacy in ("last_invalidated", "last_vote_closed", "last_next_song_changed", "last_playback_version"):
        assert not hasattr(state, legacy)
