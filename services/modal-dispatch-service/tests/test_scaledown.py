from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import pulsefm_modal_dispatch_service.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> TestClient:
    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    return TestClient(main.app)


def test_scaledown_scales_to_zero_and_reports_failed_generation(
    http: TestClient, redis_client: FakeAsyncRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    asyncio.run(redis_client.set("pulsefm:modal:call:v1", "fc-123"))
    scaled: list[int] = []

    async def fake_zero(vote_id: str) -> None:
        scaled.append(0)

    monkeypatch.setattr(main, "_set_min_instances_zero_with_retry", fake_zero)
    monkeypatch.setattr(main, "_check_generation_status", lambda call_id: "failed")

    response = http.post("/scaledown", json={"voteId": "v1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "generation": "failed"}
    assert scaled == [0]


def test_scaledown_without_call_id_still_scales_down(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scaled: list[int] = []

    async def fake_zero(vote_id: str) -> None:
        scaled.append(0)

    monkeypatch.setattr(main, "_set_min_instances_zero_with_retry", fake_zero)

    response = http.post("/scaledown", json={"voteId": "v1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "generation": "unknown"}
    assert scaled == [0]


def test_scaledown_requires_vote_id(http: TestClient) -> None:
    assert http.post("/scaledown", json={}).status_code == 400
