import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    add_voted_session,
    get_playback_current_snapshot,
    get_poll_tallies,
    has_voted_session,
    init_poll_open_atomic,
    init_poll_tally,
    init_poll_voted_set,
    playback_current_key,
    poll_tally_key,
    poll_voted_key,
    set_playback_current_snapshot,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": "OPEN"},
    }


async def test_poll_open_resets_previous_poll_state(client: FakeAsyncRedis) -> None:
    # Stale data from a previous poll with the SAME vote id (retry scenario)
    await client.hset(poll_tally_key("v1"), mapping={"a": 9, "old": 4})
    await client.sadd(poll_voted_key("v1"), "sess-old")

    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])

    assert await get_poll_tallies(client, "v1") == {"a": 0, "b": 0}
    assert not await has_voted_session(client, "v1", "sess-old")


async def test_poll_open_sets_ttls(client: FakeAsyncRedis) -> None:
    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])
    assert 0 < await client.ttl(playback_current_key()) <= 120
    assert 0 < await client.ttl(poll_tally_key("v1")) <= 240


async def test_poll_open_sets_voted_set_ttl(client: FakeAsyncRedis) -> None:
    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])
    assert 0 < await client.ttl(poll_voted_key("v1")) <= 240


async def test_voted_set_sentinel_never_reads_as_a_vote(client: FakeAsyncRedis) -> None:
    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])
    assert not await has_voted_session(client, "v1", "sess-1")
    assert await add_voted_session(client, "v1", "sess-1") is True


async def test_snapshot_roundtrip_and_corrupt_json(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    assert (await get_playback_current_snapshot(client))["poll"]["voteId"] == "v1"

    await client.set(playback_current_key(), "{not-json")
    assert await get_playback_current_snapshot(client) is None


async def test_voted_set_membership(client: FakeAsyncRedis) -> None:
    await init_poll_voted_set(client, "v1", 60)
    assert await add_voted_session(client, "v1", "sess-1") is True
    assert await add_voted_session(client, "v1", "sess-1") is False
    assert await has_voted_session(client, "v1", "sess-1") is True
    assert await has_voted_session(client, "v1", "sess-2") is False


async def test_tallies_coerce_junk_values_to_zero(client: FakeAsyncRedis) -> None:
    await init_poll_tally(client, "v1", ["a"], 60)
    await client.hset(poll_tally_key("v1"), "b", "not-a-number")
    assert await get_poll_tallies(client, "v1") == {"a": 0, "b": 0}
