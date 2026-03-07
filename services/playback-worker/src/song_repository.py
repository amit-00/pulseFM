from __future__ import annotations

from typing import Any

from helpers import parse_int, utc_ms


class SongRepository:
    def __init__(self, d1_database) -> None:
        self._db = d1_database

    async def select_next_ready_song(self, exclude_vote_id: str | None) -> dict[str, Any] | None:
        if exclude_vote_id:
            query = self._db.prepare(
                "SELECT id, duration_ms FROM songs WHERE status = 'ready' AND id != ? ORDER BY created_at DESC LIMIT 1"
            ).bind(exclude_vote_id)
        else:
            query = self._db.prepare(
                "SELECT id, duration_ms FROM songs WHERE status = 'ready' ORDER BY created_at DESC LIMIT 1"
            )

        result = await query.run()
        if isinstance(result, dict):
            rows = result.get("results", []) or []
        else:
            rows = getattr(result, "results", []) or []
        if not rows:
            return None

        first = rows[0]
        if isinstance(first, dict):
            row = first
        else:
            row = {
                "id": getattr(first, "id", None),
                "duration_ms": getattr(first, "duration_ms", None),
            }

        vote_id = row.get("id")
        duration_ms = parse_int(row.get("duration_ms"))
        if not vote_id or duration_ms is None or duration_ms <= 0:
            return None

        return {"voteId": str(vote_id), "durationMs": duration_ms}

    async def mark_song_status(self, vote_id: str, status: str) -> None:
        await self._db.prepare(
            "UPDATE songs SET status = ?, updated_at = ? WHERE id = ?"
        ).bind(status, utc_ms(), vote_id).run()
