# WP-E: Test Coverage + CI for High-Risk Existing Logic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behavioral tests for the Redis Lua/atomic helpers and the playback rotation decision logic, plus a minimal GitHub Actions CI workflow.

**Architecture:** Redis helpers get behavioral tests against fakeredis (real Lua execution). The `_rotate_song` transaction's decision core is extracted into a pure function `plan_rotation` in a new `logic.py` module (station dict + candidate list in → rotation plan out), so version gating, candidate selection, and stubbed fallback are unit-testable without Firestore. CI runs the whole pytest suite on every PR.

**Tech Stack:** pytest, pytest-asyncio, fakeredis[lua], GitHub Actions, uv.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-E section). If missing in your worktree, read `/Users/amit/Documents/repos/pulseFM/docs/superpowers/specs/2026-07-15-hardening-design.md`.
- TDD where code changes (Task 2's extraction); for pure test-adding tasks, write tests against existing behavior — if a test exposes a real bug, STOP and report it rather than changing production behavior.
- Approved new dev dependencies ONLY: `fakeredis[lua]`, `pytest`, `pytest-asyncio`.
- **Ownership fences (other WPs run in parallel):** do NOT test or modify `set_playback_poll_status` (WP-A changes it), `record_vote_atomic`/`VOTE_LUA` (WP-B deletes them), anything in `services/vote-api`, `services/playback-stream`, `services/modal-dispatch-service`, or `functions/tally-function`. In `services/playback-service/main.py`, touch ONLY the `_rotate_song`/`_select_ready_song_candidate`/`_pick_winner`/task-id-builder regions — leave `_close_vote`, `/next/refresh`, and the publish helpers alone (WP-A edits them).
- No deploys, no pushes, no terraform changes.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Behavioral tests for existing Redis helpers

**Files:**
- Modify: `packages/pulsefm-redis/pyproject.toml` — append (skip pieces that already exist):

```toml
[dependency-groups]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "fakeredis[lua]>=2.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- Test: `packages/pulsefm-redis/tests/test_poll_lifecycle.py` (create)

**Interfaces:** none produced — tests pin existing behavior of `init_poll_open_atomic`, `init_poll_tally`, `init_poll_voted_set`, `add_voted_session`, `has_voted_session`, `get_poll_tallies`, `get_playback_current_snapshot`/`set_playback_current_snapshot`.

- [ ] **Step 1: Write the tests** — `packages/pulsefm-redis/tests/test_poll_lifecycle.py`:

```python
import json

import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    add_voted_session,
    get_playback_current_snapshot,
    get_poll_tallies,
    has_voted_session,
    init_poll_open_atomic,
    init_poll_tally,
    init_poll_voted_set,
    playback_current_key,
    poll_tally_key,
    poll_voted_key,
    set_playback_current_snapshot,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": "OPEN"},
    }


async def test_poll_open_resets_previous_poll_state(client: FakeAsyncRedis) -> None:
    # Stale data from a previous poll with the SAME vote id (retry scenario)
    await client.hset(poll_tally_key("v1"), mapping={"a": 9, "old": 4})
    await client.sadd(poll_voted_key("v1"), "sess-old")

    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])

    assert await get_poll_tallies(client, "v1") == {"a": 0, "b": 0}
    assert not await has_voted_session(client, "v1", "sess-old")


async def test_poll_open_sets_ttls(client: FakeAsyncRedis) -> None:
    await init_poll_open_atomic(client, "v1", _snapshot("v1"), 120, 240, ["a", "b"])
    assert 0 < await client.ttl(playback_current_key()) <= 120
    assert 0 < await client.ttl(poll_tally_key("v1")) <= 240
    assert 0 < await client.ttl(poll_voted_key("v1")) <= 240


async def test_snapshot_roundtrip_and_corrupt_json(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    assert (await get_playback_current_snapshot(client))["poll"]["voteId"] == "v1"

    await client.set(playback_current_key(), "{not-json")
    assert await get_playback_current_snapshot(client) is None


async def test_voted_set_membership(client: FakeAsyncRedis) -> None:
    await init_poll_voted_set(client, "v1", 60)
    assert await add_voted_session(client, "v1", "sess-1") is True
    assert await add_voted_session(client, "v1", "sess-1") is False
    assert await has_voted_session(client, "v1", "sess-1") is True
    assert await has_voted_session(client, "v1", "sess-2") is False


async def test_tallies_coerce_junk_values_to_zero(client: FakeAsyncRedis) -> None:
    await init_poll_tally(client, "v1", ["a"], 60)
    await client.hset(poll_tally_key("v1"), "b", "not-a-number")
    assert await get_poll_tallies(client, "v1") == {"a": 0, "b": 0}
```

- [ ] **Step 2: Run** — `uv sync --all-packages && uv run pytest packages/pulsefm-redis/tests/test_poll_lifecycle.py -v`. Expected: PASS (these pin current behavior). If any test FAILS, that is a real finding — stop and report it in your summary instead of "fixing" the test.

- [ ] **Step 3: Commit** — `test(redis): behavioral coverage for poll lifecycle atomics`

---

### Task 2: Extract `plan_rotation` decision core from `_rotate_song`

**Files:**
- Create: `services/playback-service/pulsefm_playback_service/logic.py`
- Modify: `services/playback-service/pulsefm_playback_service/main.py` (rewire `_rotate_song`'s `_txn`, `_select_ready_song_candidate`, `_pick_winner`, task-id builders)
- Modify: `services/playback-service/pyproject.toml` (same dev-group + pytest-config block as Task 1)
- Test: `services/playback-service/tests/test_logic.py` (create)

**Interfaces:**
- Produces (in `logic.py`):

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CandidateSong:
    song_id: str
    duration_ms: int
    stubbed: bool


@dataclass(frozen=True)
class RotationPlan:
    start_at: datetime
    ends_at: datetime
    duration_ms: int
    vote_id: str
    next_vote_id: str
    next_duration_ms: int
    next_stubbed: bool
    version: int


def is_stale_version(request_version: int, current_version: int) -> bool: ...
def pick_winner(tallies: dict[str, int], rng: "random.Random | None" = None) -> str | None: ...
def select_candidate(ready_songs: list[tuple[str, dict]], current_vote_id: str | None) -> CandidateSong | None: ...
def plan_rotation(
    station: dict,
    candidate: CandidateSong | None,
    stubbed_duration_ms: int | None,
    request_version: int,
    now: datetime,
) -> RotationPlan: ...
def build_tick_task_id(vote_id: str | None, ends_at: datetime | None, version: int | None = None) -> str: ...
def build_vote_close_task_id(vote_id: str, version: int) -> str: ...
```

`plan_rotation` raises `ValueError` when `station["next"]` is missing fields or when both `candidate` and `stubbed_duration_ms` are absent. Version gating (`is_stale_version`) stays OUTSIDE `plan_rotation` — the transaction checks it first and returns `None` (noop) exactly as today. `main.py` keeps its `_txn` shape: read station → gate version → query candidates (Firestore) → call `select_candidate` on `(doc.id, doc.to_dict())` tuples → read stubbed if needed → call `plan_rotation` → apply the same `transaction.update(...)` writes as today, driven by the returned `RotationPlan`.

- [ ] **Step 1: Write the failing tests** — `services/playback-service/tests/test_logic.py`:

```python
import random
from datetime import datetime, timedelta, timezone

import pytest

from pulsefm_playback_service.logic import (
    CandidateSong,
    build_tick_task_id,
    build_vote_close_task_id,
    is_stale_version,
    pick_winner,
    plan_rotation,
    select_candidate,
)

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _station(version: int = 3) -> dict:
    return {
        "voteId": "old-song",
        "version": version,
        "next": {"voteId": "next-song", "durationMs": 90000},
    }


class TestVersionGate:
    def test_equal_version_is_stale(self) -> None:
        assert is_stale_version(request_version=3, current_version=3)

    def test_lower_version_is_stale(self) -> None:
        assert is_stale_version(request_version=2, current_version=3)

    def test_higher_version_proceeds(self) -> None:
        assert not is_stale_version(request_version=4, current_version=3)


class TestPickWinner:
    def test_clear_winner(self) -> None:
        assert pick_winner({"a": 5, "b": 2}) == "a"

    def test_tie_broken_deterministically_with_seeded_rng(self) -> None:
        assert pick_winner({"a": 3, "b": 3}, rng=random.Random(0)) in {"a", "b"}

    def test_empty_tallies(self) -> None:
        assert pick_winner({}) is None


class TestSelectCandidate:
    def test_skips_current_vote_id(self) -> None:
        songs = [("next-song", {"durationMs": 90000}), ("fresh", {"durationMs": 80000})]
        candidate = select_candidate(songs, current_vote_id="next-song")
        assert candidate == CandidateSong(song_id="fresh", duration_ms=80000, stubbed=False)

    def test_skips_missing_duration(self) -> None:
        songs = [("broken", {}), ("fresh", {"durationMs": 80000})]
        assert select_candidate(songs, None).song_id == "fresh"

    def test_no_candidates(self) -> None:
        assert select_candidate([], None) is None


class TestPlanRotation:
    def test_promotes_next_and_selects_candidate(self) -> None:
        plan = plan_rotation(
            _station(),
            candidate=CandidateSong("fresh", 80000, False),
            stubbed_duration_ms=None,
            request_version=4,
            now=NOW,
        )
        assert plan.vote_id == "next-song"
        assert plan.duration_ms == 90000
        assert plan.ends_at == NOW + timedelta(milliseconds=90000)
        assert plan.next_vote_id == "fresh"
        assert plan.next_stubbed is False
        assert plan.version == 4

    def test_falls_back_to_stubbed(self) -> None:
        plan = plan_rotation(
            _station(), candidate=None, stubbed_duration_ms=60000, request_version=4, now=NOW
        )
        assert plan.next_vote_id == "stubbed"
        assert plan.next_stubbed is True
        assert plan.next_duration_ms == 60000

    def test_missing_next_fields_raises(self) -> None:
        with pytest.raises(ValueError):
            plan_rotation(
                {"version": 3, "next": {}},
                candidate=None,
                stubbed_duration_ms=60000,
                request_version=4,
                now=NOW,
            )

    def test_no_candidate_and_no_stub_raises(self) -> None:
        with pytest.raises(ValueError):
            plan_rotation(_station(), candidate=None, stubbed_duration_ms=None, request_version=4, now=NOW)


class TestTaskIds:
    def test_tick_task_id_shape(self) -> None:
        ends = datetime(2026, 7, 15, 12, 1, 30, tzinfo=timezone.utc)
        assert build_tick_task_id("v1", ends, 4) == f"playback-v1-{int(ends.timestamp())}-4"

    def test_close_task_id_shape(self) -> None:
        assert build_vote_close_task_id("v1", 4) == "vote-close-v1-4"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest services/playback-service/tests/test_logic.py -v` → ImportError.

- [ ] **Step 3: Implement `logic.py`** so behavior matches `main.py` today exactly (this is a move-and-purify refactor, not a redesign):

```python
import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CandidateSong:
    song_id: str
    duration_ms: int
    stubbed: bool


@dataclass(frozen=True)
class RotationPlan:
    start_at: datetime
    ends_at: datetime
    duration_ms: int
    vote_id: str
    next_vote_id: str
    next_duration_ms: int
    next_stubbed: bool
    version: int


def is_stale_version(request_version: int, current_version: int) -> bool:
    return request_version <= current_version


def pick_winner(tallies: dict[str, int], rng: random.Random | None = None) -> str | None:
    if not tallies:
        return None
    chooser = rng or random
    max_votes = max(tallies.values())
    tied = [option for option, count in tallies.items() if count == max_votes]
    return chooser.choice(tied) if tied else None


def select_candidate(
    ready_songs: list[tuple[str, dict]],
    current_vote_id: str | None,
) -> CandidateSong | None:
    for song_id, data in ready_songs:
        if current_vote_id and song_id == current_vote_id:
            continue
        duration_ms = data.get("durationMs")
        if duration_ms is None:
            continue
        return CandidateSong(song_id=song_id, duration_ms=int(duration_ms), stubbed=False)
    return None


def plan_rotation(
    station: dict,
    candidate: CandidateSong | None,
    stubbed_duration_ms: int | None,
    request_version: int,
    now: datetime,
) -> RotationPlan:
    next_data = station.get("next") or {}
    promoted_vote_id = next_data.get("voteId")
    promoted_duration = next_data.get("durationMs") or next_data.get("duration")
    if promoted_vote_id is None or promoted_duration is None:
        raise ValueError("stations/main.next is missing fields")

    if candidate is None:
        if stubbed_duration_ms is None:
            raise ValueError("No ready song or stubbed song")
        candidate = CandidateSong(song_id="stubbed", duration_ms=int(stubbed_duration_ms), stubbed=True)

    duration_ms = int(promoted_duration)
    return RotationPlan(
        start_at=now,
        ends_at=now + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        vote_id=str(promoted_vote_id),
        next_vote_id=candidate.song_id,
        next_duration_ms=candidate.duration_ms,
        next_stubbed=candidate.stubbed,
        version=request_version,
    )


def build_tick_task_id(vote_id: str | None, ends_at: datetime | None, version: int | None = None) -> str:
    suffix = vote_id or ""
    timestamp = str(int(ends_at.timestamp())) if ends_at else ""
    version_suffix = str(version) if version is not None else ""
    return f"playback-{suffix}-{timestamp}-{version_suffix}"


def build_vote_close_task_id(vote_id: str, version: int) -> str:
    return f"vote-close-{vote_id}-{version}"
```

- [ ] **Step 4: Run — expect PASS** on the new tests.

- [ ] **Step 5: Rewire `main.py`** to consume `logic.py` (behavior-preserving):
- Import: `from pulsefm_playback_service.logic import CandidateSong, RotationPlan, build_tick_task_id, build_vote_close_task_id, is_stale_version, pick_winner, plan_rotation, select_candidate`.
- Delete `_pick_winner`, `_build_tick_task_id`, `_build_vote_close_task_id`; update their call sites (`_close_vote` uses `pick_winner(tallies)` — one-line change at the call, allowed despite the WP-A fence since it's the same identifier position; `_ensure_playback_tick_scheduled` and `_schedule_next_tasks` use the `build_*` functions).
- In `_txn`: replace `if request_version <= current_version: return None` with `if is_stale_version(request_version, current_version): return None`. Replace the inline candidate/stub/duration logic with: build `ready_songs` as `[(doc.id, doc.to_dict() or {}) for doc in ready_docs]` (keep the Firestore query in `_select_ready_song_candidate` or inline it — your choice, but keep the `limit(10)` and ordering), call `select_candidate`, then read the stubbed doc ONLY if `select_candidate` returned `None`, then `plan = plan_rotation(station, candidate, stubbed_duration_ms, request_version, now)` and apply the same `transaction.update` writes as before using `plan.*` fields. `_txn` returns the same dict it does today (build it from the plan) so `SongRotationResult(**result)` keeps working — or return the `RotationPlan` and map it; keep `SongRotationResult` untouched either way.

- [ ] **Step 6: Run everything** — `uv run pytest services/playback-service/tests packages/ -v` — all green.

- [ ] **Step 7: Commit** — `refactor(playback-service): extract rotation decision core into pure logic module with tests`

---

### Task 3: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow:**

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - name: Sync workspace
        run: uv sync --all-packages
      - name: Run tests
        run: uv run pytest packages/ services/ -v
```

- [ ] **Step 2: Verify locally** that the same commands pass from a clean state: `uv sync --all-packages && uv run pytest packages/ services/ -v`.

- [ ] **Step 3: Commit** — `ci: run python test suite on PRs and main`

---

### Task 4: Full verification sweep

- [ ] `uv run pytest packages/ services/ -v` — all green.
- [ ] Confirm the ownership fences held: `git diff main --stat` must show NO changes under `services/vote-api`, `services/playback-stream`, `services/modal-dispatch-service`, `functions/`, `terraform/`, or `client/`.
- [ ] Commit anything outstanding; report summary (including any pinned-behavior test that exposed a real bug).
