from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from helpers import parse_int

DEFAULT_VOTE_OPTIONS = ["energetic", "dark", "uplifting", "cinematic"]
DEFAULT_STUBBED_DURATION_MS = 300_000
DEFAULT_VOTE_CLOSE_LEAD_SECONDS = 60


@dataclass(frozen=True)
class RuntimeConfig:
    vote_options: list[str]
    options_per_window: int
    stubbed_duration_ms: int
    vote_close_lead_ms: int

    @classmethod
    def from_env(cls, env_values: dict[str, Any]) -> "RuntimeConfig":
        configured_options = [
            item.strip()
            for item in str(env_values.get("VOTE_OPTIONS", "")).split(",")
            if item.strip()
        ]
        vote_options = configured_options or list(DEFAULT_VOTE_OPTIONS)

        options_per_window = parse_int(env_values.get("OPTIONS_PER_WINDOW"), 4) or 4
        if options_per_window <= 0:
            options_per_window = 4

        stubbed_duration_ms = parse_int(
            env_values.get("STUBBED_DURATION_MS"),
            DEFAULT_STUBBED_DURATION_MS,
        ) or DEFAULT_STUBBED_DURATION_MS
        if stubbed_duration_ms <= 0:
            stubbed_duration_ms = DEFAULT_STUBBED_DURATION_MS

        vote_close_lead_seconds = parse_int(
            env_values.get("VOTE_CLOSE_LEAD_SECONDS"),
            DEFAULT_VOTE_CLOSE_LEAD_SECONDS,
        ) or DEFAULT_VOTE_CLOSE_LEAD_SECONDS
        if vote_close_lead_seconds < 0:
            vote_close_lead_seconds = 0

        return cls(
            vote_options=vote_options,
            options_per_window=options_per_window,
            stubbed_duration_ms=stubbed_duration_ms,
            vote_close_lead_ms=vote_close_lead_seconds * 1000,
        )

    def pick_vote_options(self) -> list[str]:
        if len(self.vote_options) <= self.options_per_window:
            return list(self.vote_options)
        return random.sample(self.vote_options, self.options_per_window)

    def stubbed_song(self) -> dict[str, int | str]:
        return {"voteId": "stubbed", "durationMs": self.stubbed_duration_ms}
