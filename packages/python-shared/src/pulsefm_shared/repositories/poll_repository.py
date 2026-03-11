from __future__ import annotations

"""Poll persistence adapter for create/get/close/vote workflows."""

import json
from typing import Any

from pulsefm_shared.helpers import parse_int, utc_ms


class PollRepository:
    """Repository for poll lifecycle and vote persistence."""

    def __init__(self, db) -> None:
        self.db = db

    async def create_poll(
        self,
        poll_id: str,
        options: list[str],
        start_at: int,
        end_at: int,
    ) -> None:
        """Create a new poll row."""
        now = utc_ms()
        await self.db.prepare(
            "INSERT INTO polls (id, options, start_at, end_at, is_open, winner, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, NULL, ?, ?)"
        ).bind(poll_id, json.dumps(options), start_at, end_at, now, now).run()

    async def close_poll(self, poll_id: str) -> None:
        """Close an existing poll and persist the current winning option."""
        result = await self.db.prepare(
            "SELECT option, COUNT(*) AS vote_count "
            "FROM poll_votes WHERE poll_id = ? "
            "GROUP BY option ORDER BY vote_count DESC, option ASC LIMIT 1"
        ).bind(poll_id).run()
        rows = self._extract_rows(result)
        winner = str(rows[0].get("option")) if rows and rows[0].get("option") else None

        await self.db.prepare(
            "UPDATE polls SET is_open = 0, winner = ?, updated_at = ? WHERE id = ?"
        ).bind(winner, utc_ms(), poll_id).run()

    async def get_poll(self, poll_id: str):
        """Return the poll row for ``poll_id`` or ``None``."""
        result = await self.db.prepare(
            "SELECT id, options, start_at, end_at, is_open, winner, created_at, updated_at "
            "FROM polls WHERE id = ? LIMIT 1"
        ).bind(poll_id).run()
        rows = self._extract_rows(result)
        if not rows:
            return None

        row = rows[0]
        record_id = row.get("id")
        start_at = parse_int(row.get("start_at"))
        end_at = parse_int(row.get("end_at"))
        created_at = parse_int(row.get("created_at"))
        updated_at = parse_int(row.get("updated_at"))
        if (
            not record_id
            or start_at is None
            or end_at is None
            or created_at is None
            or updated_at is None
        ):
            return None

        return {
            "id": str(record_id),
            "options": self._normalize_options(row.get("options")),
            "start_at": start_at,
            "end_at": end_at,
            "is_open": self._parse_bool(row.get("is_open")),
            "winner": self._parse_winner(row.get("winner")),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    async def upsert_vote(
        self,
        vote_id: str,
        user_id: str,
        poll_id: str,
        option: str,
    ) -> None:
        """Insert a new vote or update an existing user's vote for a poll."""
        now = utc_ms()
        await self.db.prepare(
            "INSERT INTO poll_votes (id, poll_id, user_id, option, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(poll_id, user_id) DO UPDATE SET "
            "option = excluded.option, "
            "updated_at = excluded.updated_at"
        ).bind(vote_id, poll_id, user_id, option, now, now).run()

    def _extract_rows(self, result: Any):
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

    def _normalize_options(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return [value]
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return []

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"1", "true", "t", "yes"}
        return False

    def _parse_winner(self, value: Any) -> str | None:
        if value is None:
            return None
        winner = str(value).strip()
        return winner or None
