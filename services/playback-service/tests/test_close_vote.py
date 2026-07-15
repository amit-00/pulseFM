from typing import Any

import pytest

import pulsefm_playback_service.main as main


class _FakeDoc:
    def __init__(self) -> None:
        self.written: dict[str, Any] | None = None

    async def set(self, doc: dict[str, Any]) -> None:
        self.written = doc


class _FakeCollection:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc

    def document(self, _name: str) -> _FakeDoc:
        return self._doc


class _FakeDb:
    def __init__(self, doc: _FakeDoc) -> None:
        self._doc = doc

    def collection(self, _name: str) -> _FakeCollection:
        return _FakeCollection(self._doc)


@pytest.mark.asyncio
async def test_close_vote_passes_winner_to_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []

    async def fake_get_poll_tallies(_client: Any, _vote_id: str) -> dict[str, int]:
        return {"a": 3, "b": 1}

    async def fake_set_playback_poll_status(
        _client: Any, vote_id: str, status: str, winner_option: str | None = None
    ) -> None:
        calls.append((vote_id, status, winner_option))

    monkeypatch.setattr(main, "get_redis_client", lambda: object())
    monkeypatch.setattr(main, "get_poll_tallies", fake_get_poll_tallies)
    monkeypatch.setattr(main, "set_playback_poll_status", fake_set_playback_poll_status)
    monkeypatch.setattr(main, "_publish_vote_event", lambda *a, **k: None)

    doc = _FakeDoc()
    state = {"voteId": "v1", "options": ["a", "b"], "version": 2, "status": "OPEN"}
    window = await main._close_vote(_FakeDb(doc), state)

    assert calls == [("v1", "CLOSED", "a")]
    assert window["winnerOption"] == "a"
    assert doc.written is not None and doc.written["status"] == "CLOSED"


def test_playback_events_publishing_removed() -> None:
    assert not hasattr(main, "_publish_changeover_events")
    assert not hasattr(main, "_publish_playback_event")
