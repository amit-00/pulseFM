from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest import mock

from pulsefm_encoder.main import (
    EncodedSong,
    _build_refresh_next_task_id,
    _enqueue_refresh_next_task,
    _mark_song_ready_and_enqueue_refresh,
    _persist_song_metadata,
)


class _Document:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    async def set(self, payload: dict[str, Any]) -> None:
        self.payload = payload


class _Collection:
    def __init__(self) -> None:
        self.document_id: str | None = None
        self.document_ref = _Document()

    def document(self, document_id: str) -> _Document:
        self.document_id = document_id
        return self.document_ref


class _Db:
    def __init__(self) -> None:
        self.collection_name: str | None = None
        self.collection_ref = _Collection()

    def collection(self, collection_name: str) -> _Collection:
        self.collection_name = collection_name
        return self.collection_ref


class EncoderFlowTests(unittest.TestCase):
    def test_persist_song_metadata_writes_ready_document(self) -> None:
        db = _Db()
        encoded_song = EncodedSong(vote_id="vote-123", duration_ms=42000)

        asyncio.run(_persist_song_metadata(db, encoded_song))

        self.assertEqual(db.collection_name, "songs")
        self.assertEqual(db.collection_ref.document_id, "vote-123")
        self.assertIsNotNone(db.collection_ref.document_ref.payload)
        assert db.collection_ref.document_ref.payload is not None
        self.assertEqual(db.collection_ref.document_ref.payload["durationMs"], 42000)
        self.assertEqual(db.collection_ref.document_ref.payload["status"], "ready")
        self.assertIn("createdAt", db.collection_ref.document_ref.payload)

    def test_mark_song_ready_and_enqueue_refresh_persists_before_enqueue(self) -> None:
        db = _Db()
        encoded_song = EncodedSong(vote_id="vote-123", duration_ms=42000)
        call_order: list[str] = []

        async def fake_persist(_db: _Db, _encoded_song: EncodedSong) -> None:
            call_order.append("persist")

        async def recording_to_thread(func, *args, **kwargs):
            call_order.append("to_thread")
            return func(*args, **kwargs)

        def fake_enqueue(vote_id: str) -> None:
            call_order.append(f"enqueue:{vote_id}")

        with (
            mock.patch("pulsefm_encoder.main._persist_song_metadata", fake_persist),
            mock.patch("pulsefm_encoder.main.asyncio.to_thread", recording_to_thread),
            mock.patch("pulsefm_encoder.main._enqueue_refresh_next_task", fake_enqueue),
        ):
            asyncio.run(_mark_song_ready_and_enqueue_refresh(db, encoded_song))

        self.assertEqual(call_order, ["persist", "to_thread", "enqueue:vote-123"])

    def test_enqueue_refresh_next_task_uses_expected_task_contract(self) -> None:
        calls: list[dict[str, Any]] = []

        def fake_enqueue_json_task(queue_name: str, target_url: str, payload: dict[str, Any], **kwargs: Any) -> None:
            calls.append({
                "queue_name": queue_name,
                "target_url": target_url,
                "payload": payload,
                "kwargs": kwargs,
            })

        with (
            mock.patch("pulsefm_encoder.main.enqueue_json_task", fake_enqueue_json_task),
            mock.patch("pulsefm_encoder.main._playback_refresh_url", lambda: "https://playback-service/next/refresh"),
        ):
            _enqueue_refresh_next_task("vote-123")

        self.assertEqual(calls, [{
            "queue_name": "playback-queue",
            "target_url": "https://playback-service/next/refresh",
            "payload": {"voteId": "vote-123"},
            "kwargs": {
                "task_id": "next-song-refresh-vote-123",
                "ignore_already_exists": True,
            },
        }])

    def test_build_refresh_next_task_id(self) -> None:
        self.assertEqual(_build_refresh_next_task_id("vote-123"), "next-song-refresh-vote-123")


if __name__ == "__main__":
    unittest.main()
