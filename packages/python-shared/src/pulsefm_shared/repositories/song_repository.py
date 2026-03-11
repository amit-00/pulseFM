from __future__ import annotations

"""Song persistence adapter with typed contracts for callers."""

from pulsefm_shared.helpers import parse_int, utc_ms


class SongRepository:
    """Repository for selecting and transitioning songs in storage."""

    def __init__(self, db) -> None:
        self.db = db

    async def get_next_ready_song(
        self,
        exclude_song_ids: set[str] | None = None,
    ):
        """Return the next valid ready song not in ``exclude_song_ids``."""
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

        return {
            "songId": str(song_id),
            "duration_ms": duration_ms,
        }

    async def mark_song_queued(self, song_id: str) -> None:
        """Mark a song as queued to avoid duplicate selection."""
        await self.db.prepare(
            "UPDATE songs SET status = 'queued', updated_at = ? WHERE id = ?"
        ).bind(utc_ms(), song_id).run()

    async def mark_song_played(self, song_id: str) -> None:
        """Mark a promoted song as played."""
        await self.db.prepare(
            "UPDATE songs SET status = 'played', updated_at = ? WHERE id = ?"
        ).bind(utc_ms(), song_id).run()

    def _extract_rows(self, result):
        if isinstance(result, dict):
            rows = result.get("results", []) or []
        else:
            rows = getattr(result, "results", []) or []

        extracted = []
        for item in rows:
            if isinstance(item, dict):
                extracted.append(item)
            else:
                extracted.append(item)
        return extracted

