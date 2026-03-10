from __future__ import annotations

from typing import Any

from pulsefm_playback_worker.helpers import parse_int, utc_ms


class SongRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def get_next_ready_song(
        self,
        exclude_song_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        excluded = sorted(exclude_song_ids or set())
        placeholders = ", ".join("?" for _ in excluded)

        sql = "SELECT id, duration_ms FROM songs WHERE status = 'ready'"
        if excluded:
            sql += f" AND id NOT IN ({placeholders})"
        sql += " ORDER BY created_at ASC LIMIT 1"

        query = self.db.prepare(sql)
        if excluded:
            query = query.bind(*excluded)

        result = await query.run()
        rows = self._extract_rows(result)
        if not rows:
            return None

        row = rows[0]
        song_id = row.get("id")
        duration_ms = parse_int(row.get("duration_ms"))
        if not song_id or duration_ms is None or duration_ms <= 0:
            return None

        return {"songId": str(song_id), "duration_ms": duration_ms}

    async def mark_song_queued(self, song_id: str) -> None:
        await self.db.prepare(
            "UPDATE songs SET status = 'queued', updated_at = ? WHERE id = ?"
        ).bind(utc_ms(), song_id).run()

    async def mark_song_played(self, song_id: str) -> None:
        await self.db.prepare(
            "UPDATE songs SET status = 'played', updated_at = ? WHERE id = ?"
        ).bind(utc_ms(), song_id).run()

    def _extract_rows(self, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, dict):
            rows = result.get("results", []) or []
        else:
            rows = getattr(result, "results", []) or []

        extracted: list[dict[str, Any]] = []
        for item in rows:
            if isinstance(item, dict):
                extracted.append(item)
            else:
                extracted.append(
                    {
                        "id": getattr(item, "id", None),
                        "duration_ms": getattr(item, "duration_ms", None),
                    }
                )
        return extracted

