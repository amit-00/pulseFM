# WP-B: Synchronous Vote Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vote-api records the vote atomically in Redis during the request and returns the authoritative result; the async tally pipeline (tally-function, tally-queue, tally topic) is deleted.

**Architecture:** A single Lua script (`SUBMIT_VOTE_LUA`) validates the poll (current voteId, OPEN status, option exists) and performs the dedup + increment in one Redis round-trip, using `cjson` to read the playback snapshot. vote-api maps its result to HTTP codes. Nothing publishes tally events anymore — clients poll `/state` (WP-A).

**Tech Stack:** FastAPI, redis.asyncio + Lua, Terraform, pytest + fakeredis[lua] + FastAPI TestClient.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-B section). If missing in your worktree, read `/Users/amit/Documents/repos/pulseFM/docs/superpowers/specs/2026-07-15-hardening-design.md`.
- TDD: failing test → minimal code → pass → commit. Python ≥3.11, strict annotations.
- Approved new dev dependencies ONLY: `fakeredis[lua]`, `pytest`, `pytest-asyncio`. fakeredis's Lua engine (lupa) supports `cjson` — required here.
- This WP OWNS deletion of: `functions/tally-function/`, `google_cloud_tasks_queue.tally_queue`, `google_pubsub_topic.tally_events`, tally blocks in `terraform/functions.tf`, and tally envs in the vote-api block of `terraform/cloud_run.tf`. Do NOT touch `terraform/eventarc.tf` (WP-A deletes the tally trigger there).
- No `terraform apply`, no deploys, no pushes. Verify with `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`.
- IMPORTANT (merge coordination): if `terraform/eventarc.tf` still contains `google_eventarc_trigger.playback_stream_tally` when you run validate (WP-A not merged yet), `terraform validate` will fail after you delete the `tally_events` topic. In that case, verify with `terraform validate` EXPECTED-FAIL only on that one missing reference, note it in your report, and rely on the merge step to resolve. Do not delete WP-A's trigger yourself.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `submit_vote_atomic` in pulsefm-redis

**Files:**
- Modify: `packages/pulsefm-redis/pulsefm_redis/client.py`
- Modify: `packages/pulsefm-redis/pyproject.toml` (dev deps — see below; skip any part WP-A already merged)
- Test: `packages/pulsefm-redis/tests/test_submit_vote.py` (create)

**Interfaces:**
- Produces: `async def submit_vote_atomic(client: redis.Redis, vote_id: str, session_id: str, option: str) -> str` returning one of: `"ok"`, `"duplicate"`, `"closed"`, `"not_current"`, `"invalid_option"`, `"no_state"`.
- Deletes: `record_vote_atomic` and module-level `VOTE_LUA` (superseded; tally-function's copy dies with the function).

- [ ] **Step 1: Ensure dev deps exist** in `packages/pulsefm-redis/pyproject.toml` (append if absent):

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

Run `uv sync --all-packages`.

- [ ] **Step 2: Write the failing tests** — `packages/pulsefm-redis/tests/test_submit_vote.py`:

```python
import pytest
from fakeredis import FakeAsyncRedis

from pulsefm_redis.client import (
    init_poll_open_atomic,
    set_playback_current_snapshot,
    submit_vote_atomic,
)


@pytest.fixture
def client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


def _snapshot(vote_id: str, status: str = "OPEN") -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": status},
    }


async def _open_poll(client: FakeAsyncRedis, vote_id: str = "v1") -> None:
    await init_poll_open_atomic(client, vote_id, _snapshot(vote_id), 3600, 3600, ["a", "b"])


async def test_first_vote_counts(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "ok"
    assert await client.hget("pulsefm:poll:v1:tally", "a") == "1"


async def test_duplicate_session_rejected_and_not_double_counted(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    await submit_vote_atomic(client, "v1", "sess-1", "a")
    assert await submit_vote_atomic(client, "v1", "sess-1", "b") == "duplicate"
    assert await client.hget("pulsefm:poll:v1:tally", "a") == "1"
    assert await client.hget("pulsefm:poll:v1:tally", "b") == "0"


async def test_closed_poll_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    await set_playback_current_snapshot(client, _snapshot("v1", status="CLOSED"), 3600)
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "closed"


async def test_stale_vote_id_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client, "v2")
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "not_current"


async def test_unknown_option_rejected(client: FakeAsyncRedis) -> None:
    await _open_poll(client)
    assert await submit_vote_atomic(client, "v1", "sess-1", "zzz") == "invalid_option"


async def test_missing_snapshot_reports_no_state(client: FakeAsyncRedis) -> None:
    assert await submit_vote_atomic(client, "v1", "sess-1", "a") == "no_state"
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/pulsefm-redis/tests/test_submit_vote.py -v`
Expected: FAIL — `ImportError: cannot import name 'submit_vote_atomic'`.

- [ ] **Step 4: Implement.** In `client.py`, replace `VOTE_LUA` + `record_vote_atomic` with:

```python
SUBMIT_VOTE_LUA = """
local playback_key = KEYS[1]
local tally_key = KEYS[2]
local voted_key = KEYS[3]

local vote_id = ARGV[1]
local session_id = ARGV[2]
local option = ARGV[3]

local raw = redis.call("GET", playback_key)
if not raw then
  return "no_state"
end

local ok, snapshot = pcall(cjson.decode, raw)
if not ok or type(snapshot) ~= "table" or type(snapshot["poll"]) ~= "table" then
  return "no_state"
end

local poll = snapshot["poll"]
if poll["voteId"] ~= vote_id then
  return "not_current"
end
if poll["status"] ~= "OPEN" then
  return "closed"
end
if redis.call("HEXISTS", tally_key, option) == 0 then
  return "invalid_option"
end

if redis.call("SADD", voted_key, session_id) == 1 then
  redis.call("HINCRBY", tally_key, option, 1)
  return "ok"
end
return "duplicate"
"""


async def submit_vote_atomic(
    client: redis.Redis,
    vote_id: str,
    session_id: str,
    option: str,
) -> str:
    result = await client.eval(
        SUBMIT_VOTE_LUA,
        3,
        playback_current_key(),
        poll_tally_key(vote_id),
        poll_voted_key(vote_id),
        vote_id,
        session_id,
        option,
    )  # type: ignore[misc]
    return str(result)
```

- [ ] **Step 5: Run — expect PASS**: `uv run pytest packages/pulsefm-redis/tests -v`. Then confirm `record_vote_atomic` has no remaining callers before its deletion: `grep -rn record_vote_atomic services/ packages/ functions/` — the only hits should be the deleted definition (tally-function has its own inline copy, deleted in Task 3).

- [ ] **Step 6: Commit** — `feat(redis): single-round-trip atomic vote validation + dedup + tally`

---

### Task 2: vote-api uses the atomic path

**Files:**
- Modify: `services/vote-api/pulsefm_vote_api/main.py` (replace `_validate_vote` + enqueue with `submit_vote_atomic`)
- Modify: `services/vote-api/pulsefm_vote_api/config.py` (delete `vote_queue_name`, `tally_function_url` — the Settings class becomes empty; delete `config.py` and its import entirely)
- Modify: `services/vote-api/pyproject.toml` (remove `pulsefm-tasks` dependency if listed; add dev-dep group as in Task 1 plus `httpx>=0.27` which TestClient requires — httpx is test-only)
- Test: `services/vote-api/tests/test_vote_endpoint.py` (create)

**Interfaces:**
- Consumes: `submit_vote_atomic` (Task 1).
- Produces HTTP contract for `POST /vote`:
  - 200 `{"status": "ok"}` — counted
  - 409 `detail="Duplicate vote"` — dedup hit
  - 409 `detail="Vote closed"` — poll CLOSED
  - 400 `detail="Invalid voteId"` — not the current poll
  - 400 `detail="Invalid option"` — unknown option
  - 503 `detail="Vote state unavailable"` — no snapshot in Redis
  - 503 `detail="Voting temporarily unavailable (Redis unreachable)"` — Redis error
  - 400s for missing session header / voteId / option (unchanged)

- [ ] **Step 1: Write the failing tests** — `services/vote-api/tests/test_vote_endpoint.py`:

```python
from typing import Iterator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import pulsefm_vote_api.main as main
from pulsefm_redis.client import init_poll_open_atomic


def _snapshot(vote_id: str) -> dict:
    return {
        "currentSong": {"voteId": "s1", "startAt": 1, "endAt": 2, "durationMs": 1},
        "nextSong": {"voteId": "s2", "durationMs": 1},
        "poll": {"voteId": vote_id, "options": ["a", "b"], "version": 1, "status": "OPEN"},
    }


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    with TestClient(main.app) as client:
        yield client


def _vote(http: TestClient, session: str = "sess-1", option: str = "a") -> "object":
    return http.post(
        "/vote",
        json={"voteId": "v1", "option": option},
        headers={"X-Session-Id": session},
    )


def _seed_open_poll(redis_client: FakeAsyncRedis) -> None:
    import asyncio

    asyncio.run(init_poll_open_atomic(redis_client, "v1", _snapshot("v1"), 3600, 3600, ["a", "b"]))


def test_vote_counts_and_returns_ok(http: TestClient, redis_client: FakeAsyncRedis) -> None:
    _seed_open_poll(redis_client)
    response = _vote(http)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_duplicate_returns_409(http: TestClient, redis_client: FakeAsyncRedis) -> None:
    _seed_open_poll(redis_client)
    assert _vote(http).status_code == 200
    duplicate = _vote(http)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Duplicate vote"


def test_no_snapshot_returns_503(http: TestClient) -> None:
    response = _vote(http)
    assert response.status_code == 503


def test_missing_session_header_400(http: TestClient) -> None:
    response = http.post("/vote", json={"voteId": "v1", "option": "a"})
    assert response.status_code == 400
```

NOTE: fakeredis state lives on the instance (its in-memory fake server), not on an event loop, so seeding with `asyncio.run(...)` before TestClient drives the app on its own loop is safe. If `asyncio.run` inside the seeded helper conflicts with TestClient's loop on this fakeredis version, switch the seeding to an async pytest fixture that runs before the TestClient fixture — pick whichever variant is green and simple.

- [ ] **Step 2: Run to verify failure** — new behaviors (409 detail, 503) don't exist yet. `uv run pytest services/vote-api/tests -v` → FAIL.

- [ ] **Step 3: Implement.** New `services/vote-api/pulsefm_vote_api/main.py` (complete file):

```python
import logging
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, status

from pulsefm_redis.client import get_redis_client, submit_vote_atomic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="PulseFM Vote API", version="2.0.0")

_RESULT_TO_ERROR: Dict[str, tuple[int, str]] = {
    "duplicate": (status.HTTP_409_CONFLICT, "Duplicate vote"),
    "closed": (status.HTTP_409_CONFLICT, "Vote closed"),
    "not_current": (status.HTTP_400_BAD_REQUEST, "Invalid voteId"),
    "invalid_option": (status.HTTP_400_BAD_REQUEST, "Invalid option"),
    "no_state": (status.HTTP_503_SERVICE_UNAVAILABLE, "Vote state unavailable"),
}


@app.post("/vote")
async def submit_vote(
    payload: Dict[str, Any],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> Dict[str, str]:
    if not x_session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing session id")

    vote_id = payload.get("voteId")
    option = payload.get("option")
    if not isinstance(vote_id, str) or not vote_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing voteId")
    if not isinstance(option, str) or not option:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing option")

    try:
        result = await submit_vote_atomic(get_redis_client(), vote_id, x_session_id, option)
    except Exception:
        logger.exception("Vote submission failed", extra={"voteId": vote_id, "sessionId": x_session_id})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voting temporarily unavailable (Redis unreachable)",
        )

    if result == "ok":
        logger.info("Vote counted", extra={"voteId": vote_id, "sessionId": x_session_id, "option": option})
        return {"status": "ok"}

    error_status, detail = _RESULT_TO_ERROR.get(
        result, (status.HTTP_500_INTERNAL_SERVER_ERROR, f"Unexpected vote result: {result}")
    )
    logger.info("Vote rejected", extra={"voteId": vote_id, "sessionId": x_session_id, "result": result})
    raise HTTPException(status_code=error_status, detail=detail)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy"}
```

Delete `services/vote-api/pulsefm_vote_api/config.py`. Remove `pulsefm-tasks` from `services/vote-api/pyproject.toml` dependencies (check what's listed first). Run `uv sync --all-packages`.

- [ ] **Step 4: Run — expect PASS**: `uv run pytest services/vote-api/tests packages/pulsefm-redis/tests -v`.

- [ ] **Step 5: Commit** — `feat(vote-api)!: authoritative synchronous vote path`

---

### Task 3: Delete the tally pipeline (code + Terraform)

**Files:**
- Delete: `functions/tally-function/` (entire directory)
- Modify: `terraform/functions.tf` — delete: `data.archive_file.tally_function`, `google_storage_bucket_object.tally_function_source`, `google_cloudfunctions2_function.tally_function`, `google_cloudfunctions2_function_iam_member.tally_function_invoker`, `google_cloud_run_v2_service_iam_member.tally_function_run_invoker` (lines 1–59)
- Modify: `terraform/cloudtasks.tf` — delete `google_cloud_tasks_queue.tally_queue`
- Modify: `terraform/pubsub.tf` — delete `google_pubsub_topic.tally_events`
- Modify: `terraform/cloud_run.tf` vote_api block — delete the `TALLY_FUNCTION_URL`, `VOTE_QUEUE_NAME`, and `TASKS_OIDC_SERVICE_ACCOUNT` env blocks (vote-api no longer enqueues anything). Keep `ENCODED_BUCKET`/`ENCODED_PREFIX` (unrelated).
- Check: `terraform/service_accounts.tf` + `terraform/iam.tf` for `tally_function` service account and its role bindings — delete those too (grep: `grep -rn tally terraform/`). Also delete `google_service_account_iam_member.vote_api_act_as_self` ONLY IF it exists solely for Cloud Tasks OIDC (it does — vote-api no longer mints task tokens; verify no other use before deleting: `grep -rn "vote_api" terraform/iam.tf`).

- [ ] **Step 1: Make all deletions above.**

- [ ] **Step 2: Validate.** `grep -rn "tally" terraform/` — remaining hits must ONLY be in `terraform/eventarc.tf` (WP-A's file — leave it; see Global Constraints for the expected validate failure if it's still present) . Then `cd terraform && terraform init -backend=false && terraform validate`.

- [ ] **Step 3: Confirm workspace still syncs**: `uv sync --all-packages` (root `pyproject.toml` uses `functions/*` glob — deleting the directory is sufficient; but check `[tool.uv.sources]` in the root `pyproject.toml` for a `pulsefm-tally-function` entry and remove it if present). `grep -rn "tally" pyproject.toml README.md` — clean README references are WP-F's job; only fix `pyproject.toml`.

- [ ] **Step 4: Run all tests**: `uv run pytest packages/ services/ -v` — expect PASS.

- [ ] **Step 5: Commit** — `feat(infra)!: delete async tally pipeline (function, queue, topic)`

---

### Task 4: Client surfaces authoritative vote results

**Files:**
- Modify: `client/app/api/vote/route.ts`
- Modify: `client/hooks/useStreamPlayer.ts` (`submitVote` only — coordinate: WP-A also edits this file, different function)

**Interfaces:**
- Consumes: vote-api HTTP contract from Task 2.
- Produces: `/api/vote` passes through the backend status code and `{ error: <detail> }`; `submitVote` treats 409-duplicate as "already voted" (keeps optimistic selection) instead of a generic failure.

- [ ] **Step 1: Update `client/app/api/vote/route.ts`.** Replace the `if (!response.ok)` block:

```typescript
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      return NextResponse.json(
        { error: body.detail || "Vote request failed" },
        { status: response.status }
      );
    }
```

- [ ] **Step 2: Update `submitVote` in `useStreamPlayer.ts`.** Replace the `if (!response.ok)` handling inside the `try`:

```typescript
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { error?: string };
        if (response.status === 409 && data.error === "Duplicate vote") {
          // The backend confirmed this session already voted — keep the selection.
          return;
        }
        throw new Error(data.error || "Vote failed");
      }
```

(The `catch` block that rolls back `hasVoted`/`selectedOption` stays for real failures.)

- [ ] **Step 3: Verify**: `cd client && npm install && npx tsc --noEmit && npm run build` — expect success.

- [ ] **Step 4: Commit** — `feat(client): surface authoritative vote results (duplicate/closed)`

---

### Task 5: Full verification sweep

- [ ] `uv run pytest packages/ services/ -v` — all green.
- [ ] `cd terraform && terraform validate && terraform fmt -check` (see Global Constraints for the one tolerated failure mode pre-merge).
- [ ] `cd client && npx tsc --noEmit && npm run build`.
- [ ] `grep -rn "tally-function\|tally_queue\|TALLY_FUNCTION_URL\|record_vote_atomic" services/ packages/ functions/ terraform/ client/` — no hits (except possibly `terraform/eventarc.tf`).
- [ ] `git diff main --stat` — only WP-B files. Commit anything outstanding; report summary.
