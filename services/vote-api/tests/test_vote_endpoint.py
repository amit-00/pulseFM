from typing import Iterator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import pulsefm_vote_api.main as main
from pulsefm_redis.client import init_poll_open_atomic


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": "OPEN"},
    }


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    with TestClient(main.app) as client:
        yield client


def _vote(http: TestClient, session: str = "sess-1", option: str = "a") -> "object":
    return http.post(
        "/vote",
        json={"voteId": "v1", "option": option},
        headers={"X-Session-Id": session},
    )


def _seed_open_poll(redis_client: FakeAsyncRedis) -> None:
    import asyncio

    asyncio.run(init_poll_open_atomic(redis_client, "v1", _snapshot("v1"), 3600, 3600, ["a", "b"]))


def test_vote_counts_and_returns_ok(http: TestClient, redis_client: FakeAsyncRedis) -> None:
    _seed_open_poll(redis_client)
    response = _vote(http)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_duplicate_returns_409(http: TestClient, redis_client: FakeAsyncRedis) -> None:
    _seed_open_poll(redis_client)
    assert _vote(http).status_code == 200
    duplicate = _vote(http)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Duplicate vote"


def test_no_snapshot_returns_503(http: TestClient) -> None:
    response = _vote(http)
    assert response.status_code == 503


def test_missing_session_header_400(http: TestClient) -> None:
    response = http.post("/vote", json={"voteId": "v1", "option": "a"})
    assert response.status_code == 400
