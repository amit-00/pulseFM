# WP-C: Modal Dispatch Fire-and-Forget + Secret Manager + Timeouts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The CLOSE webhook spawns generation without blocking, scale-down happens via a delayed idempotent Cloud Task that also reports generation failures, and Modal tokens live in Secret Manager.

**Architecture:** `_handle_close_event` becomes: lock → scale up → `.spawn()` → store call id in Redis → enqueue delayed `/scaledown` task → mark done → unlock. `/scaledown` always scales `min_containers` to 0 (safe: Modal never kills in-flight calls on autoscaler updates) and polls the stored call id purely for observability. Terraform moves both Modal tokens to Secret Manager (`nextjs_session_signing_key` pattern) and adds explicit timeouts to all Cloud Run services except playback-stream (WP-A owns that block).

**Tech Stack:** FastAPI, modal SDK (`.spawn()`, `modal.functions.FunctionCall`), redis.asyncio, Cloud Tasks, Terraform Secret Manager, pytest + fakeredis + monkeypatched modal.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-C section). If missing in your worktree, read `/Users/amit/Documents/repos/pulseFM/docs/superpowers/specs/2026-07-15-hardening-design.md`.
- TDD: failing test → minimal code → pass → commit. Python ≥3.11, strict annotations.
- Approved new dev dependencies ONLY: `fakeredis[lua]`, `pytest`, `pytest-asyncio`, `httpx` (TestClient). Never import real Modal credentials in tests — monkeypatch every `modal.*` touchpoint.
- Do NOT edit the `playback_stream` service block in `terraform/cloud_run.tf` (WP-A owns it). Do not touch `terraform/eventarc.tf`, `terraform/pubsub.tf`.
- No `terraform apply`, no deploys, no pushes. Verify: `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Spawn instead of block; schedule scale-down

**Files:**
- Modify: `services/modal-dispatch-service/pulsefm_modal_dispatch_service/main.py`
- Modify: `services/modal-dispatch-service/pulsefm_modal_dispatch_service/config.py`
- Modify: `services/modal-dispatch-service/pyproject.toml` (add dev group: pytest, pytest-asyncio, fakeredis[lua], httpx; add `[tool.pytest.ini_options] asyncio_mode = "auto"`)
- Test: `services/modal-dispatch-service/tests/test_close_event.py` (create)

**Interfaces:**
- Produces:
  - `def _modal_call_key(vote_id: str) -> str` → `f"pulsefm:modal:call:{vote_id}"`
  - `def _spawn_modal_generation(vote_id: str, winner_option: str) -> str` — calls `method.spawn(...)`, returns `call.object_id`
  - `def _scaledown_url() -> str` → `f"{base}/scaledown"` (same shape as `_warmup_url`)
  - New setting: `generation_horizon_seconds: int = int(os.getenv("GENERATION_HORIZON_SECONDS", "600"))`
  - `_handle_close_event` response statuses unchanged (`ok`, `skipped`, `already_processed`, `in_progress`) — Eventarc contract intact.

- [ ] **Step 1: Write the failing tests** — `services/modal-dispatch-service/tests/test_close_event.py`:

```python
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis

import pulsefm_modal_dispatch_service.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> dict[str, Any]:
    calls: dict[str, Any] = {"spawned": [], "min_instances": [], "tasks": []}

    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)

    async def fake_has_listeners() -> bool:
        return True

    monkeypatch.setattr(main, "_has_active_listeners", fake_has_listeners)
    monkeypatch.setattr(main, "_set_modal_min_instances", lambda n: calls["min_instances"].append(n))

    def fake_spawn(vote_id: str, winner_option: str) -> str:
        calls["spawned"].append((vote_id, winner_option))
        return "fc-123"

    monkeypatch.setattr(main, "_spawn_modal_generation", fake_spawn)

    def fake_enqueue(queue: str, url: str, payload: dict, delay: float, task_id=None, ignore_already_exists=True):
        calls["tasks"].append({"url": url, "payload": payload, "delay": delay, "task_id": task_id})
        return "task-name"

    monkeypatch.setattr(main, "enqueue_json_task_with_delay", fake_enqueue)
    monkeypatch.setattr(main.settings, "modal_dispatch_service_url", "https://dispatch.example", raising=False)
    return calls


async def test_close_spawns_and_schedules_scaledown(harness: dict[str, Any], redis_client: FakeAsyncRedis) -> None:
    result = await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})

    assert result == {"status": "ok"}
    assert harness["spawned"] == [("v1", "jazz")]
    assert harness["min_instances"] == [1]  # no inline scale-down anymore
    assert await redis_client.get("pulsefm:modal:call:v1") == "fc-123"

    (task,) = harness["tasks"]
    assert task["url"] == "https://dispatch.example/scaledown"
    assert task["payload"] == {"voteId": "v1"}
    assert task["delay"] == main.settings.generation_horizon_seconds
    assert task["task_id"] == "modal-scaledown-v1"

    assert await redis_client.get("pulsefm:modal:close:v1:done") == "1"
    assert await redis_client.get("pulsefm:modal:close:v1:lock") is None  # released


async def test_close_is_idempotent(harness: dict[str, Any], redis_client: FakeAsyncRedis) -> None:
    await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    result = await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    assert result == {"status": "already_processed"}
    assert len(harness["spawned"]) == 1


async def test_spawn_failure_releases_lock_and_does_not_mark_done(
    harness: dict[str, Any], redis_client: FakeAsyncRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(vote_id: str, winner_option: str) -> str:
        raise RuntimeError("modal down")

    monkeypatch.setattr(main, "_spawn_modal_generation", boom)
    with pytest.raises(RuntimeError):
        await main._handle_close_event({"voteId": "v1", "winnerOption": "jazz"})
    assert await redis_client.get("pulsefm:modal:close:v1:done") is None
    assert await redis_client.get("pulsefm:modal:close:v1:lock") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest services/modal-dispatch-service/tests/test_close_event.py -v`
Expected: FAIL — `_spawn_modal_generation` does not exist; close path still blocks on `_dispatch_modal_generation` and scales down inline.

- [ ] **Step 3: Implement.** In `config.py` add `generation_horizon_seconds: int = int(os.getenv("GENERATION_HORIZON_SECONDS", "600"))`. In `main.py`:

Add helpers:

```python
def _modal_call_key(vote_id: str) -> str:
    return f"pulsefm:modal:call:{vote_id}"


def _scaledown_url() -> str:
    base = settings.modal_dispatch_service_url.rstrip("/")
    if not base:
        raise ValueError("MODAL_DISPATCH_SERVICE_URL is required")
    return f"{base}/scaledown"


def _spawn_modal_generation(vote_id: str, winner_option: str) -> str:
    descriptor = _get_descriptor(winner_option)
    music_cls = modal.Cls.from_name(settings.modal_app_name, settings.modal_class_name)
    generator = music_cls()
    method = getattr(generator, settings.modal_method_name)
    call = method.spawn(
        genre=descriptor["genre"],
        mood=descriptor["mood"],
        energy=descriptor["energy"],
        vote_id=vote_id,
    )
    return str(call.object_id)


async def _store_modal_call_id(vote_id: str, call_id: str) -> None:
    try:
        client = get_redis_client()
        await client.set(_modal_call_key(vote_id), call_id, ex=max(60, settings.generation_horizon_seconds * 2))  # type: ignore[misc]
    except Exception:
        logger.warning("Redis unavailable for storing modal call id", extra={"voteId": vote_id})
```

Replace the body of the `try:` in `_handle_close_event` (keep the listener check, lock acquisition, and `finally: await _release_close_lock(vote_id)` exactly as they are):

```python
    try:
        if not await _has_active_listeners():
            logger.info("Skipping modal generation due to no listeners", extra={"voteId": vote_id})
            await _mark_close_done(vote_id)
            return {"status": "skipped"}

        await _set_min_instances(1)
        logger.info("Scaled modal min_instances to 1", extra={"voteId": vote_id})

        call_id = await asyncio.to_thread(_spawn_modal_generation, vote_id, winner_option)
        await _store_modal_call_id(vote_id, call_id)
        logger.info("Modal generation spawned", extra={"voteId": vote_id, "callId": call_id})

        enqueue_json_task_with_delay(
            settings.modal_queue_name,
            _scaledown_url(),
            {"voteId": vote_id},
            settings.generation_horizon_seconds,
            task_id=f"modal-scaledown-{vote_id}",
            ignore_already_exists=True,
        )

        await _mark_close_done(vote_id)
        return {"status": "ok"}
    finally:
        await _release_close_lock(vote_id)
```

Delete `_dispatch_modal_generation` and `_set_min_instances_zero_with_retry`'s call site in the close path (the retry helper itself is reused by `/scaledown` in Task 2 — keep the function).

- [ ] **Step 4: Run — expect PASS**: `uv run pytest services/modal-dispatch-service/tests -v`.

- [ ] **Step 5: Commit** — `feat(modal-dispatch)!: spawn generation fire-and-forget; scale-down via delayed task`

---

### Task 2: `/scaledown` endpoint with failure observability

**Files:**
- Modify: `services/modal-dispatch-service/pulsefm_modal_dispatch_service/main.py`
- Test: `services/modal-dispatch-service/tests/test_scaledown.py` (create)

**Interfaces:**
- Produces: `POST /scaledown` body `{"voteId": "<id>"}` → `{"status": "ok", "generation": "succeeded" | "failed" | "running" | "unknown"}`. Always attempts `min_containers=0` via `_set_min_instances_zero_with_retry`; generation status is best-effort logging only.
- Produces: `def _check_generation_status(call_id: str) -> str` — wraps `modal.functions.FunctionCall.from_id(call_id).get(timeout=0)`; returns `"succeeded"`, `"running"` (on `TimeoutError`), or `"failed"` (any other exception).

- [ ] **Step 1: Write the failing tests** — `services/modal-dispatch-service/tests/test_scaledown.py`:

```python
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

import pulsefm_modal_dispatch_service.main as main


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch, redis_client: FakeAsyncRedis) -> TestClient:
    monkeypatch.setattr(main, "get_redis_client", lambda: redis_client)
    return TestClient(main.app)


def test_scaledown_scales_to_zero_and_reports_failed_generation(
    http: TestClient, redis_client: FakeAsyncRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    asyncio.run(redis_client.set("pulsefm:modal:call:v1", "fc-123"))
    scaled: list[int] = []

    async def fake_zero(vote_id: str) -> None:
        scaled.append(0)

    monkeypatch.setattr(main, "_set_min_instances_zero_with_retry", fake_zero)
    monkeypatch.setattr(main, "_check_generation_status", lambda call_id: "failed")

    response = http.post("/scaledown", json={"voteId": "v1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "generation": "failed"}
    assert scaled == [0]


def test_scaledown_without_call_id_still_scales_down(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scaled: list[int] = []

    async def fake_zero(vote_id: str) -> None:
        scaled.append(0)

    monkeypatch.setattr(main, "_set_min_instances_zero_with_retry", fake_zero)

    response = http.post("/scaledown", json={"voteId": "v1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "generation": "unknown"}
    assert scaled == [0]


def test_scaledown_requires_vote_id(http: TestClient) -> None:
    assert http.post("/scaledown", json={}).status_code == 400
```

- [ ] **Step 2: Run to verify failure** — 404 on `/scaledown`. `uv run pytest services/modal-dispatch-service/tests/test_scaledown.py -v`.

- [ ] **Step 3: Implement.** In `main.py`:

```python
def _check_generation_status(call_id: str) -> str:
    try:
        modal.functions.FunctionCall.from_id(call_id).get(timeout=0)
        return "succeeded"
    except TimeoutError:
        return "running"
    except Exception:
        return "failed"


async def _get_modal_call_id(vote_id: str) -> str | None:
    try:
        client = get_redis_client()
        value = await client.get(_modal_call_key(vote_id))  # type: ignore[misc]
        return str(value) if value else None
    except Exception:
        logger.warning("Redis unavailable for modal call id lookup", extra={"voteId": vote_id})
        return None


@app.post("/scaledown")
async def scaledown(payload: Dict[str, Any]) -> Dict[str, str]:
    vote_id = payload.get("voteId")
    if not isinstance(vote_id, str) or not vote_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voteId is required")

    await _set_min_instances_zero_with_retry(vote_id)

    generation = "unknown"
    call_id = await _get_modal_call_id(vote_id)
    if call_id:
        generation = await asyncio.to_thread(_check_generation_status, call_id)

    if generation == "failed":
        logger.error(
            "Modal generation failed; station will fall back to stubbed song",
            extra={"voteId": vote_id, "callId": call_id},
        )
    elif generation == "running":
        logger.warning(
            "Modal generation still running at scale-down horizon",
            extra={"voteId": vote_id, "callId": call_id},
        )

    return {"status": "ok", "generation": generation}
```

(If `TimeoutError` in the installed modal SDK is `modal.exception.FunctionTimeoutError` or the builtin — check `python -c "import modal; help(modal.functions.FunctionCall.get)"` quickly; catch both if ambiguous: `except (TimeoutError, Exception)` is WRONG — keep the specific-then-generic order shown above and add the modal-specific timeout class to the first `except` clause if it exists.)

- [ ] **Step 4: Run — expect PASS**: `uv run pytest services/modal-dispatch-service/tests -v`.

- [ ] **Step 5: Commit** — `feat(modal-dispatch): idempotent /scaledown with generation-failure logging`

---

### Task 3: Terraform — Secret Manager tokens + service timeouts

**Files:**
- Modify: `terraform/secrets.tf` (add two secrets, versions, accessor bindings)
- Modify: `terraform/cloud_run.tf` (modal env blocks → `value_source`; timeouts for vote_api, encoder, playback_service, modal_dispatch_service; NOT playback_stream)

- [ ] **Step 1: Append to `terraform/secrets.tf`:**

```hcl
resource "google_secret_manager_secret" "modal_token_id" {
  secret_id = "modal-token-id"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "modal_token_id" {
  secret      = google_secret_manager_secret.modal_token_id.id
  secret_data = var.modal_token_id
}

resource "google_secret_manager_secret_iam_member" "modal_token_id_accessor" {
  secret_id = google_secret_manager_secret.modal_token_id.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.modal_dispatch_service.email}"
}

resource "google_secret_manager_secret" "modal_token_secret" {
  secret_id = "modal-token-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "modal_token_secret" {
  secret      = google_secret_manager_secret.modal_token_secret.id
  secret_data = var.modal_token_secret
}

resource "google_secret_manager_secret_iam_member" "modal_token_secret_accessor" {
  secret_id = google_secret_manager_secret.modal_token_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.modal_dispatch_service.email}"
}
```

- [ ] **Step 2: In `terraform/cloud_run.tf` modal_dispatch_service block**, replace the two plaintext env blocks (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`) with:

```hcl
      env {
        name = "MODAL_TOKEN_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.modal_token_id.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "MODAL_TOKEN_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.modal_token_secret.secret_id
            version = "latest"
          }
        }
      }
```

Also add to the same container env list: `env { name = "GENERATION_HORIZON_SECONDS" value = "600" }`.

- [ ] **Step 3: Add timeouts** inside each `template` block (after `service_account`), NOT touching playback_stream:
- vote_api: `timeout = "30s"`
- encoder: `timeout = "300s"` (transcodes audio)
- playback_service: `timeout = "120s"` (Firestore transaction + task scheduling)
- modal_dispatch_service: `timeout = "60s"` (nothing blocks anymore)

- [ ] **Step 4: Validate**

Run: `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`
Expected: valid, no fmt diffs. Note: `var.modal_token_id`/`var.modal_token_secret` already exist in `variables.tf` with `sensitive = true` and cloudbuild already passes them — no pipeline change. State still contains the secret values (inherent to TF-managed secret versions); WP-F documents this residual risk.

- [ ] **Step 5: Commit** — `infra: modal tokens via Secret Manager; explicit Cloud Run timeouts`

---

### Task 4: Full verification sweep

- [ ] `uv run pytest services/modal-dispatch-service/tests packages/ -v` — green.
- [ ] `cd terraform && terraform validate && terraform fmt -check` — green.
- [ ] `grep -rn "\.remote(\|_dispatch_modal_generation" services/` — no hits. `grep -rn "value = var.modal_token" terraform/` — no hits.
- [ ] `git diff main --stat` — only WP-C files. Commit anything outstanding; report summary.
