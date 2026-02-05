import fakeredis

from pulsefm_vote_api.redis_keys import dedupe_key


def test_dedupe_key_and_set():
    client = fakeredis.FakeRedis(decode_responses=True)
    key = dedupe_key("window1", "session1")
    assert client.set(key, "option-a", nx=True, ex=10)
    assert client.set(key, "option-b", nx=True, ex=10) is None
