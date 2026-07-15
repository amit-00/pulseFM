# WP-A: Replace SSE with Client Polling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the SSE streaming stack; clients poll `GET /state` (~2s with jitter) and derive UI transitions by diffing snapshots.

**Architecture:** playback-stream shrinks to a cached read API over Redis/Firestore. playback-service writes `winnerOption` into the Redis snapshot at vote close (replacing the deleted VOTE_CLOSED event). The Eventarc triggers feeding playback-stream and the now-consumerless `playback` Pub/Sub topic are deleted. The client's `useStreamPlayer` hook polls and diffs.

**Tech Stack:** FastAPI, redis.asyncio, google-cloud-firestore (AsyncClient), Next.js/React 19, Terraform (google provider), uv workspace, pytest + fakeredis.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-A section) — read it first. If the spec is missing in your worktree, read it from `/Users/amit/Documents/repos/pulseFM/docs/superpowers/specs/2026-07-15-hardening-design.md`.
- TDD: failing test → minimal code → pass → commit. Python ≥3.11. Strict type annotations on all new functions.
- Approved new dev dependencies ONLY: `fakeredis[lua]`, `pytest`, `pytest-asyncio`. No other new packages.
- Do NOT delete the `tally` Pub/Sub topic or anything in `terraform/cloudtasks.tf` / `terraform/functions.tf` — WP-B owns those.
- Do NOT run `terraform apply`, deploy anything, or push to remotes. Verify Terraform with `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`.
- Run Python tests with `uv run pytest <path> -v` from the repo root (after `uv sync --all-packages`).
- Client verification: `cd client && npm install && npx tsc --noEmit && npm run build`.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `set_playback_poll_status` carries `winner_option`

**Files:**
- Modify: `packages/pulsefm-redis/pulsefm_redis/client.py:50-75` (`set_playback_poll_status`)
- Modify: `packages/pulsefm-redis/pyproject.toml` (add dev dependency group)
- Test: `packages/pulsefm-redis/tests/test_poll_status.py` (create; also create empty `packages/pulsefm-redis/tests/__init__.py` if pytest collection requires it — it should not with rootdir config, so skip unless needed)

**Interfaces:**
- Produces: `async def set_playback_poll_status(client: redis.Redis, vote_id: str, status: str, winner_option: str | None = None) -> None` — sets `poll["status"]` and, when `winner_option is not None`, `poll["winnerOption"]`.

- [ ] **Step 1: Add dev deps to `packages/pulsefm-redis/pyproject.toml`** (append at end of file):

```toml
[dependency-groups]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "fakeredis[lua]>=2.23",
]
```

Run: `uv sync --all-packages` — expect success.

- [ ] **Step 2: Write the failing test** — `packages/pulsefm-redis/tests/test_poll_status.py`:

```python
import json

import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    get_playback_current_snapshot,
    playback_current_key,
    set_playback_current_snapshot,
    set_playback_poll_status,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "song-1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "song-2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 3, "status": "OPEN"},
    }


@pytest.mark.asyncio
async def test_close_writes_status_and_winner(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    await set_playback_poll_status(client, "v1", "CLOSED", winner_option="a")
    snapshot = await get_playback_current_snapshot(client)
    assert snapshot["poll"]["status"] == "CLOSED"
    assert snapshot["poll"]["winnerOption"] == "a"


@pytest.mark.asyncio
async def test_status_only_leaves_winner_absent(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    await set_playback_poll_status(client, "v1", "CLOSED")
    snapshot = await get_playback_current_snapshot(client)
    assert snapshot["poll"]["status"] == "CLOSED"
    assert "winnerOption" not in snapshot["poll"]


@pytest.mark.asyncio
async def test_vote_id_mismatch_raises(client: FakeAsyncRedis) -> None:
    await set_playback_current_snapshot(client, _snapshot("v1"), 60)
    with pytest.raises(ValueError):
        await set_playback_poll_status(client, "other", "CLOSED", winner_option="a")
```

If `pytest.mark.asyncio` needs config, add to `packages/pulsefm-redis/pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/pulsefm-redis/tests/test_poll_status.py -v`
Expected: FAIL — `set_playback_poll_status() got an unexpected keyword argument 'winner_option'`.

- [ ] **Step 4: Implement.** In `client.py`, change the signature and poll mutation:

```python
async def set_playback_poll_status(
    client: redis.Redis,
    vote_id: str,
    status: str,
    winner_option: str | None = None,
) -> None:
```

and after `poll["status"] = status` add:

```python
    if winner_option is not None:
        poll["winnerOption"] = winner_option
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest packages/pulsefm-redis/tests -v` — expect PASS. Also run the pre-existing suite: `uv run pytest packages/pulsefm-auth/tests -v` — expect PASS.

- [ ] **Step 6: Commit** — `feat(redis): allow poll close to record winnerOption in snapshot`

---

### Task 2: playback-service writes winner to Redis at close and stops publishing playback events

**Files:**
- Modify: `services/playback-service/pulsefm_playback_service/main.py`
- Modify: `services/playback-service/pulsefm_playback_service/config.py` (remove `playback_events_topic` field if present)
- Test: `services/playback-service/tests/test_close_vote.py` (create)
- Modify: `services/playback-service/pyproject.toml` (same `[dependency-groups]`/pytest config block as Task 1 Step 1)

**Interfaces:**
- Consumes: `set_playback_poll_status(client, vote_id, "CLOSED", winner_option=...)` from Task 1.
- Produces: no playback-events Pub/Sub publishes anywhere in this service (`_publish_changeover_events` deleted; `NEXT-SONG-CHANGED` publish in `/next/refresh` deleted). `_publish_vote_event` (vote-events topic) is UNCHANGED — modal-dispatch consumes it.

- [ ] **Step 1: Write the failing test** — `services/playback-service/tests/test_close_vote.py`. `_close_vote` is async and takes `(db, state)`; stub Firestore and Redis at module seams with monkeypatch:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/playback-service/tests/test_close_vote.py -v`
Expected: FAIL — the fake records `("v1", "CLOSED", None)` because `_close_vote` doesn't pass the winner yet.

- [ ] **Step 3: Implement.** In `main.py` `_close_vote` (line ~364), change:

```python
        await set_playback_poll_status(get_redis_client(), vote_id, "CLOSED")
```

to:

```python
        await set_playback_poll_status(get_redis_client(), vote_id, "CLOSED", winner_option=winner_option)
```

- [ ] **Step 4: Run test — expect PASS. Commit** — `feat(playback-service): record winnerOption in redis snapshot on vote close`

- [ ] **Step 5: Remove playback-event publishes (test first).** Add to the same test file:

```python
def test_playback_events_publishing_removed() -> None:
    assert not hasattr(main, "_publish_changeover_events")
    assert not hasattr(main, "_publish_playback_event")
```

Run — expect FAIL. Then in `main.py`:
- Delete `_publish_playback_event` and `_publish_changeover_events`.
- In `/tick` (line ~769): delete the entire `try/except` block around `_publish_changeover_events(rotation, request_version)` and its success log line.
- In `/next/refresh` (line ~718): keep the `_reconcile_next_song_snapshot` call and `redis_changed` handling, but delete the `_publish_playback_event("NEXT-SONG-CHANGED", ...)` call and the now-unused `canonical_version`/`canonical_vote_id`/`canonical_duration_ms` locals.
- In `config.py`: delete the `playback_events_topic` settings field (grep first: `grep -n playback_events services/playback-service -r`).

- [ ] **Step 6: Run — expect PASS**: `uv run pytest services/playback-service/tests -v`. Then confirm nothing else references the removed names: `grep -rn "playback_events\|_publish_playback_event\|PLAYBACK_EVENTS_TOPIC" services/ packages/ functions/` — expect no hits in Python code.

- [ ] **Step 7: Commit** — `refactor(playback-service): remove playback-events publishes (no consumers after SSE removal)`

---

### Task 3: playback-stream becomes a pure read API

**Files:**
- Modify: `services/playback-stream/pulsefm_playback_stream/main.py` (large deletion)
- Modify: `services/playback-stream/pulsefm_playback_stream/config.py`
- Modify: `services/playback-stream/pyproject.toml` (dev deps + pytest config, same block as Task 1 Step 1)
- Test: `services/playback-stream/tests/test_state.py` (create)

**Interfaces:**
- Produces: `GET /state` — same JSON shape as today (`currentSong`, `nextSong`, `poll` incl. `tallies` + `winnerOption`, `listeners`, `redisAvailable`, `ts`); `GET /health`. Nothing else.
- `StreamState` keeps ONLY: `snapshot_cache`, `tally_caches`, `tally_lock`, `listener_cache`, `listener_lock`, `set_snapshot`, `clear_snapshot`, `reset_tallies`.

- [ ] **Step 1: Write the failing tests** — `services/playback-stream/tests/test_state.py`:

```python
import json
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import pulsefm_playback_stream.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_state_serves_winner_from_snapshot(
    monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis
) -> None:
    snapshot = {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 9999999999999, "durationMs": 100000},
        "nextSong": {"voteId": "s2", "durationMs": 100000},
        "poll": {"voteId": "v1", "options": ["a", "b"], "version": 5, "status": "CLOSED", "winnerOption": "b"},
    }
    await redis_client.set("pulsefm:playback:current", json.dumps(snapshot))
    await redis_client.hset("pulsefm:poll:v1:tally", mapping={"a": 2, "b": 7})

    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    main.app.state.stream = main.StreamState()

    with TestClient(main.app) as http:
        body = http.get("/state").json()

    assert body["poll"]["winnerOption"] == "b"
    assert body["poll"]["tallies"] == {"a": 2, "b": 7}
    assert body["redisAvailable"] is True


def test_sse_surface_removed() -> None:
    paths = {route.path for route in main.app.routes}
    assert "/stream" not in paths
    assert not any(p.startswith("/events/") for p in paths)
    assert "/state" in paths and "/health" in paths


def test_stream_state_has_no_event_markers() -> None:
    state = main.StreamState()
    for legacy in ("last_invalidated", "last_vote_closed", "last_next_song_changed", "last_playback_version"):
        assert not hasattr(state, legacy)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/playback-stream/tests/test_state.py -v`
Expected: FAIL on `test_sse_surface_removed` and `test_stream_state_has_no_event_markers`.

- [ ] **Step 3: Implement the deletion.** In `main.py`, DELETE:
- `_format_sse`, `_extract_poll` stays (still used by `/state`), `_LoopState`, `_check_marker_events`, `_check_timed_events`, `_event_stream`, `@app.get("/stream")`, all three `@app.post("/events/...")` handlers, `_handle_next_song_changed_event`, `_handle_changeover_event`, `_next_song_conflicts`, `_build_tally_snapshot_payload`, `_build_hello_payload`.
- On `StreamState`: the fields/methods `last_invalidated`, `last_vote_closed`, `last_next_song_changed`, `last_playback_version`, `is_tally_dirty`, `mark_tally_dirty`, `invalidate`, `record_vote_closed`, `record_next_song_changed`, `is_stale_event`, `winner_for_vote`, `stream_event_markers`. On `CachedValue`: remove `dirty`/`mark_dirty` and the `self.dirty` check inside `is_fresh` (nothing marks dirty anymore).
- Imports that become unused (`StreamingResponse`, `AsyncGenerator`, `dataclass`, `decode_pubsub_json`, `HTTPException`, `Request`, `status`) and the `TALLY_CACHE_STALENESS_MS` constant stays (used by `_get_tallies_cached`).
- In `/state` (line ~634): replace the `if poll.get("winnerOption") is None: poll["winnerOption"] = s.winner_for_vote(vote_id)` block with nothing — `winnerOption` now flows from the Redis snapshot (Task 1/2) or the Firestore fallback (`_build_state_snapshot` already maps it). Ensure the key is always present: after `poll["tallies"] = tallies` add `poll.setdefault("winnerOption", None)`.
- In `config.py`: delete `stream_interval_ms`, `tally_snapshot_interval_sec`, `heartbeat_sec` (grep to confirm no remaining users).
- Check `pulsefm-pubsub` is still needed: `grep -rn pulsefm_pubsub services/playback-stream/` — if no hits, remove it from `services/playback-stream/pyproject.toml` dependencies.

- [ ] **Step 4: Run — expect all PASS**: `uv run pytest services/playback-stream/tests -v`.

- [ ] **Step 5: Commit** — `refactor(playback-stream)!: remove SSE stack; /state is the read API`

---

### Task 4: Terraform — delete stream triggers + playback topic, add timeout

**Files:**
- Modify: `terraform/eventarc.tf` (delete `playback_stream_tally`, `playback_stream_changeover`, `playback_stream_vote_events` resources — keep `encoder_finalize` and `modal_dispatch_vote_events`)
- Modify: `terraform/pubsub.tf` (delete `google_pubsub_topic.playback_events` only; `tally_events` stays — WP-B owns it)
- Modify: `terraform/cloud_run.tf` (playback_service block: delete the `PLAYBACK_EVENTS_TOPIC` env; playback_stream block: add `timeout = "60s"` inside `template`, directly after `service_account`)

- [ ] **Step 1: Make the edits above.** Note `terraform/functions.tf` references `google_pubsub_topic.tally_events` (leave alone) — verify nothing still references `playback_events`: `grep -rn playback_events terraform/` must return no hits after the edit.

- [ ] **Step 2: Validate**

Run: `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`
Expected: `Success! The configuration is valid.` and no fmt diffs.

- [ ] **Step 3: Commit** — `infra: drop SSE eventarc triggers and playback topic; explicit playback-stream timeout`

---

### Task 5: Client — polling hook

**Files:**
- Create: `client/lib/pollDiff.ts` (pure diffing helpers — keeps the hook thin and future-testable)
- Modify: `client/hooks/useStreamPlayer.ts`
- Delete: `client/app/api/playback/stream/route.ts`
- Modify: `client/lib/types.ts` (delete `HelloEvent`, `TallySnapshotEvent`, `TallyDeltaEvent`, `SongChangedEvent`, `NextSongChangedEvent`, `VoteClosedEvent`)

**Interfaces:**
- Produces (in `client/lib/pollDiff.ts`):

```typescript
import { PlaybackStateSnapshot } from "@/lib/types";

export const POLL_INTERVAL_MS = 2000;
export const POLL_JITTER_MS = 500;
export const BOUNDARY_GRACE_MS = 300;

export type SnapshotTransitions = {
  songChanged: boolean;
  nextSongChanged: boolean;
  voteClosed: boolean;
  pollChanged: boolean;
};

export function diffSnapshots(
  prev: PlaybackStateSnapshot | null,
  next: PlaybackStateSnapshot,
): SnapshotTransitions {
  if (!prev) {
    return { songChanged: false, nextSongChanged: false, voteClosed: false, pollChanged: false };
  }
  return {
    songChanged: prev.currentSong.voteId !== next.currentSong.voteId,
    nextSongChanged:
      prev.nextSong.voteId !== next.nextSong.voteId ||
      prev.nextSong.durationMs !== next.nextSong.durationMs,
    voteClosed: prev.poll.status === "OPEN" && next.poll.status === "CLOSED",
    pollChanged: prev.poll.voteId !== next.poll.voteId,
  };
}

export function nextPollDelayMs(snapshot: PlaybackStateSnapshot | null, now: number): number {
  const jitter = Math.floor(Math.random() * POLL_JITTER_MS);
  const base = POLL_INTERVAL_MS + jitter;
  const songEndAt = snapshot?.currentSong?.endAt ?? null;
  if (songEndAt && songEndAt > now) {
    // Wake just after the changeover boundary if it lands before the next regular poll.
    const untilBoundary = songEndAt - now + BOUNDARY_GRACE_MS;
    if (untilBoundary < base) return Math.max(250, untilBoundary);
  }
  return base;
}
```

- [ ] **Step 1: Create `client/lib/pollDiff.ts`** with exactly the content above.

- [ ] **Step 2: Rewire the hook.** In `useStreamPlayer.ts`:

Delete: `connectStream` entirely, `streamRef`, `reconnectTimerRef`, `reconnectAttemptRef`, `queuedSongChangedRef`, `songChangedInFlightRef`, `flushSongChangedQueue`, `processSongChangedEvent`, `pollVersionRef`, `playbackVersionRef`, the constants `SONG_CHANGE_RETRY_ATTEMPTS`/`RECONNECT_*`, the event-type imports from `@/lib/types`, and the `connectStream()` call + stream cleanup in the init effect.

Add a polling effect (after the init effect). Note `applySongChangeover` and `refreshState` already exist and are reused unchanged; `applySnapshotTransitions` centralizes the diff handling:

```typescript
  const applySnapshotTransitions = useCallback(
    async (prev: PlaybackStateSnapshot | null, next: PlaybackStateSnapshot) => {
      const transitions = diffSnapshots(prev, next);
      if (transitions.songChanged) {
        try {
          await applySongChangeover(next);
          setStreamError(null);
        } catch {
          setStreamError("Failed to apply song changeover");
        }
      } else if (transitions.nextSongChanged && next.nextSong.voteId) {
        loadTrackToSlot(getInactiveSlot(activeSlotRef.current), getAudioUrl(next.nextSong.voteId));
      }
      if (transitions.pollChanged) {
        const voteStatus = await fetchVoteStatus(next.poll.voteId);
        setHasVoted(voteStatus.hasVoted);
        setSelectedOption(voteStatus.selectedOption);
      }
    },
    [applySongChangeover, getInactiveSlot, loadTrackToSlot],
  );

  useEffect(() => {
    if (!sessionReady) return;
    let cancelled = false;
    let timerId: number | null = null;

    const poll = async () => {
      if (cancelled) return;
      const prev = snapshotRef.current;
      try {
        const next = await fetchPlaybackState();
        if (cancelled) return;
        snapshotRef.current = next;
        setSnapshot(next);
        setActiveListeners(typeof next.listeners === "number" ? next.listeners : null);
        if (typeof next.redisAvailable === "boolean") setRedisAvailable(next.redisAvailable);
        await applySnapshotTransitions(prev, next);
        setStreamError(null);
      } catch {
        if (!cancelled) setStreamError("Failed to fetch playback state");
      } finally {
        if (!cancelled) {
          timerId = window.setTimeout(poll, nextPollDelayMs(snapshotRef.current, Date.now()));
        }
      }
    };

    timerId = window.setTimeout(poll, nextPollDelayMs(snapshotRef.current, Date.now()));
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [applySnapshotTransitions, sessionReady]);
```

Also: in `submitVote`, after a successful (`response.ok`) vote, add an immediate `void refreshState().catch(() => {});` so tallies update without waiting for the next poll. Update the misleading comment in the media-error effect ("stream-driven") to "poll-driven". Import `diffSnapshots` is not needed in the hook if only used inside `applySnapshotTransitions` — import `nextPollDelayMs` and `diffSnapshots` from `@/lib/pollDiff`.

Note on `refreshState`: it stays as-is (used at init and post-vote). The dedicated poll loop intentionally does NOT call `fetchVoteStatus` every tick — only on `pollChanged`.

- [ ] **Step 3: Delete `client/app/api/playback/stream/route.ts`** and the event interfaces in `client/lib/types.ts`. Grep for stragglers: `grep -rn "EventSource\|TallyDelta\|TallySnapshotEvent\|SongChangedEvent\|HelloEvent\|VoteClosedEvent\|NextSongChangedEvent\|/api/playback/stream" client/ --include="*.ts" --include="*.tsx"` — expect no hits.

- [ ] **Step 4: Verify**

Run: `cd client && npm install && npx tsc --noEmit && npm run build`
Expected: both succeed with zero errors.

- [ ] **Step 5: Commit** — `feat(client)!: poll /state instead of SSE; derive transitions by snapshot diffing`

---

### Task 6: Full verification sweep

- [ ] Run: `uv run pytest packages/ services/ -v` (all suites), `cd terraform && terraform validate`, `cd client && npx tsc --noEmit && npm run build`.
- [ ] `git diff main --stat` — confirm only WP-A files changed. Confirm `grep -rn "STREAM_INTERVAL_MS\|/events/tally\|/events/playback" services/ terraform/` has no hits (playback-stream's `/events/vote` for modal-dispatch in eventarc.tf `modal_dispatch_vote_events` MUST still exist).
- [ ] Commit anything outstanding; report summary.
