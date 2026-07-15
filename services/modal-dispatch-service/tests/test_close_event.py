import dataclasses
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis

import pulsefm_modal_dispatch_service.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> dict[str, Any]:
    calls: dict[str, Any] = {"spawned": [], "min_instances": [], "tasks": []}

    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)

    async def fake_has_listeners() -> bool:
        return True

    monkeypatch.setattr(main, "_has_active_listeners", fake_has_listeners)
    monkeypatch.setattr(main, "_set_modal_min_instances", lambda n: calls["min_instances"].append(n))

    def fake_spawn(vote_id: str, winner_option: str) -> str:
        calls["spawned"].append((vote_id, winner_option))
        return "fc-123"

    monkeypatch.setattr(main, "_spawn_modal_generation", fake_spawn)

    def fake_enqueue(queue: str, url: str, payload: dict, delay: float, task_id=None, ignore_already_exists=True):
        calls["tasks"].append({"url": url, "payload": payload, "delay": delay, "task_id": task_id})
        return "task-name"

    monkeypatch.setattr(main, "enqueue_json_task_with_delay", fake_enqueue)
    # Settings is a frozen dataclass, so swap the module-level instance for a copy.
    monkeypatch.setattr(
        main,
        "settings",
        dataclasses.replace(main.settings, modal_dispatch_service_url="https://dispatch.example"),
    )
    return calls


async def test_close_spawns_and_schedules_scaledown(harness: dict[str, Any], redis_client: FakeAsyncRedis) -> None:
    result = await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})

    assert result == {"status": "ok"}
    assert harness["spawned"] == [("v1", "jazz")]
    assert harness["min_instances"] == [1]  # no inline scale-down anymore
    assert await redis_client.get("pulsefm:modal:call:v1") == "fc-123"

    (task,) = harness["tasks"]
    assert task["url"] == "https://dispatch.example/scaledown"
    assert task["payload"] == {"voteId": "v1"}
    assert task["delay"] == main.settings.generation_horizon_seconds
    assert task["task_id"] == "modal-scaledown-v1"

    assert await redis_client.get("pulsefm:modal:close:v1:done") == "1"
    assert await redis_client.get("pulsefm:modal:close:v1:lock") is None  # released


async def test_close_is_idempotent(harness: dict[str, Any], redis_client: FakeAsyncRedis) -> None:
    await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    result = await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    assert result == {"status": "already_processed"}
    assert len(harness["spawned"]) == 1


async def test_spawn_failure_releases_lock_and_does_not_mark_done(
    harness: dict[str, Any], redis_client: FakeAsyncRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(vote_id: str, winner_option: str) -> str:
        raise RuntimeError("modal down")

    monkeypatch.setattr(main, "_spawn_modal_generation", boom)
    with pytest.raises(RuntimeError):
        await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    assert await redis_client.get("pulsefm:modal:close:v1:done") is None
    assert await redis_client.get("pulsefm:modal:close:v1:lock") is None
