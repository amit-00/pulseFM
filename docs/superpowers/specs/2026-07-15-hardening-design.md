# PulseFM Hardening — Design Spec

**Date:** 2026-07-15
**Status:** Approved by Amit (conversation, 2026-07-15)
**Source:** External engineering review of the repository (5 ill-advised decisions, 4 questionable ones)

## Goal

Harden PulseFM against every point raised in the engineering review. The user-approved
directions are:

1. Replace SSE streaming with client polling of `/state` (chosen over fixing SSE in place).
2. Make the vote path synchronous and honest (client gets the authoritative result).
3. Make Modal dispatch fire-and-forget via `.spawn()`; scale-down cannot strand GPU spend.
4. Move Modal tokens into Secret Manager (pattern already exists for the Next.js key).
5. Add real test coverage for the highest-risk logic + a minimal CI workflow.
6. Front the songs bucket with signed URLs; remove `allUsers` access.
7. Document the non-code review points (Cloudflare migration ADR, tradeoffs section).

Out of scope (explicitly accepted limits): Redis basic-tier durability (tallies/dedupe are
lost on failover; users may re-vote once), a WebSocket/push-platform migration, CDN
fronting, and the review's authorship-interview point (addressed only via docs).

## Work Packages

### WP-A — Replace SSE with polling (review points 1 & 2)

**Problem.** `services/playback-stream` holds every SSE client open with a
`while True: sleep(0.05)` loop (busy-poll, one Cloud Run concurrency slot per listener,
no configured request timeout), and `StreamState` keeps authoritative event markers in
per-instance memory, so replicas can disagree about dirty tallies, vote closes, and
playback versions.

**Server changes (`services/playback-stream`).**
- Keep `GET /state` and `GET /health`. Delete `GET /stream`, `_event_stream`,
  `_LoopState`, `_check_marker_events`, `_check_timed_events`, and the SSE formatting
  helpers.
- Delete the three Eventarc ingest endpoints (`POST /events/tally`, `/events/playback`,
  `/events/vote`) and the event-marker fields on `StreamState`
  (`last_invalidated`, `last_vote_closed`, `last_next_song_changed`,
  `last_playback_version`, dirty-flag machinery).
- `StreamState` reduces to short-TTL read-through caches over shared stores:
  playback snapshot (TTL = song `endAt`), tallies (~500 ms staleness), listener count
  (~1 s staleness). Per-instance divergence is bounded by these TTLs (≤ ~1–2 s skew)
  and documented as a deliberate tradeoff.
- `/state` response keeps its current shape (snapshot + `poll.tallies` +
  `winnerOption` + `listeners` + `redisAvailable`); `winnerOption` now comes from the
  Redis snapshot / Firestore fallback instead of in-memory event markers.

**Upstream change (`services/playback-service` + `packages/pulsefm-redis`).**
- When closing a vote, write `winnerOption` into the Redis playback snapshot
  (extend `set_playback_poll_status` or add a sibling helper). Today only `status`
  flips in Redis and the winner traveled via the deleted SSE event.

**Dead infrastructure removed (Terraform + code).**
- Eventarc triggers targeting playback-stream (tally, playback, vote-events →
  `/events/*`).
- The `tally` Pub/Sub topic loses its only consumer here, but its **deletion is owned
  by WP-B** (which deletes the rest of the tally pipeline) to avoid worktree collisions.
- The `playback` events topic and the `_publish_changeover_events` /
  `NEXT-SONG-CHANGED` / `CHANGEOVER` publishes in playback-service (no consumers
  remain).
- The `vote-events` topic **stays** — modal-dispatch-service consumes OPEN/CLOSE.
- Explicit `timeout` set on the playback-stream Cloud Run service (polls are
  millisecond requests; the timeout is hygiene, not a streaming contract).

**Client changes (`client/`).**
- Replace the EventSource machinery in `hooks/useStreamPlayer.ts` with a polling hook:
  - fetch `/api/playback/state` every ~2 s **with jitter** (avoid synchronized herds),
  - immediate refetch after submitting a vote,
  - a scheduled fetch at the known `endAt` boundary so changeover feels instant.
- UI transitions are derived by diffing consecutive snapshots: `currentSong.voteId`
  change ⇒ song changed; `poll.status` OPEN→CLOSED ⇒ vote closed (winner from
  `winnerOption`); `nextSong` change ⇒ next-song changed.
- Audio scheduling already runs off `startAt`/`endAt`; only tally freshness drops to
  ~2 s (accepted).
- Delete the `/api/playback/stream` proxy route.

**Load envelope.** 1,000 concurrent listeners ≈ 500 req/s of cache-served reads;
Redis is touched a few times per second per instance regardless of listener count.

### WP-B — Synchronous, honest vote path (review point Q1)

**Problem.** vote-api returns 200 after enqueuing a Cloud Task; the authoritative
Lua dedupe happens later in tally-function. A vote can silently fail to count.

**Changes.**
- vote-api validates and then runs the `VOTE_LUA` dedupe/increment
  (`record_vote_atomic` in `packages/pulsefm-redis`) directly in the request.
  Response is authoritative: counted (200 `{"status":"ok"}`), duplicate (409),
  closed (409), invalid option/voteId (400), Redis down (503).
- Consolidate validation + dedupe so a vote costs ~1 Redis round-trip instead of 4
  sequential calls (extend the Lua script to check poll status/option existence, or
  pipeline the reads).
- No tally event is published — polling removed the only consumer.
- **Delete (owned by WP-B):** `functions/tally-function`, the `tally-queue` Cloud
  Tasks queue, the `tally` topic, the enqueue path in vote-api, and all related
  Terraform/IAM.
- Client `/api/vote` route and vote handler surface duplicate/closed states to the
  user (status-code plumbing largely exists; verify and adjust copy).

**Accepted tradeoff.** Loses queue-absorbs-spikes; the Lua call is O(1) and the real
ceilings (vote-api instances, shared VPC connector throughput) are far beyond hobby
scale.

### WP-C — Modal dispatch: fire-and-forget + Secret Manager + timeouts (points 3 & 4)

**Problem.** The CLOSE webhook blocks on a synchronous `.remote()` GPU call inside an
Eventarc push request (default 300 s timeout, none configured), risking mid-flight
kills, a stuck `min_containers=1`, and unreliable lock release. Modal tokens are
plaintext env vars in `terraform/cloud_run.tf` despite the Secret Manager pattern
existing in `terraform/secrets.tf`.

**Changes (`services/modal-dispatch-service`).**
- Replace `.remote()` with `.spawn()`; store the Modal function-call id in Redis
  (keyed by voteId, TTL ~= generation horizon), mark close-done immediately after a
  successful spawn, release the lock.
- New idempotent `POST /scaledown` endpoint, driven by a **delayed Cloud Task**
  enqueued at spawn time (delay = generation horizon). It:
  - sets `min_containers=0` using the existing retry helper (a SIGTERM elsewhere can
    no longer strand warm GPU instances),
  - polls the stored function-call id and logs ERROR if the generation job failed
    (restores the failure signal `.remote()` used to provide; rotation already falls
    back to the stubbed song).
- `update_autoscaler(min_containers=0)` does not kill in-flight calls, so an
  overlapping next-vote generation is safe (worst case: a lost warm start).

**Terraform.**
- `modal_token_id` / `modal_token_secret`: Secret Manager secrets + versions +
  scoped `secretAccessor` binding for the modal-dispatch SA (copy the
  `nextjs_session_signing_key` pattern), consumed via `value_source.secret_key_ref`.
- Explicit `timeout` blocks on all Cloud Run services (vote-api, encoder,
  playback-service, modal-dispatch-service; playback-stream handled in WP-A).

### WP-D — Private bucket + signed URLs (review point Q2)

**Problem.** `pulsefm-generated-songs` grants `roles/storage.objectViewer` to
`allUsers` (terraform/iam.tf).

**Changes.**
- Remove the `allUsers` binding; grant `objectViewer` to the Next.js server SA.
- Next.js server mints **V4 signed URLs via IAM Credentials `signBlob`** (keyless WIF;
  the SA needs `roles/iam.serviceAccountTokenCreator` on itself). Terraform adds that
  binding.
- New server route returns the signed URL for a track. Mint **one URL per track**
  (not per user), ~1 h expiry, cached server-side; on signing failure serve the
  last-known unexpired URL.
- Client stops composing public bucket URLs; it fetches the signed URL and
  **prefetches the next track's URL** when the poll diff shows `nextSong` changed.

**Accepted tradeoffs (documented).** Audio delivery now depends on the WIF/IAM chain,
and unique query strings defeat shared HTTP caches (higher GCS egress per listener).
If scale ever outweighs privacy, this is the first WP to revisit.

### WP-E — Tests + CI for high-risk existing logic (review point 5)

- **New dev dependencies (approved): `fakeredis[lua]`, `pytest-asyncio`.**
- `packages/pulsefm-redis`: behavioral tests against fakeredis's real Lua execution —
  `VOTE_LUA` (first vote counts, duplicate doesn't, per-option increments),
  `POLL_OPEN_LUA` (atomic reset of snapshot/tally/voted keys, TTLs), snapshot helpers.
- `services/playback-service`: extract pure decision logic into testable functions —
  version gating (`request_version <= current` ⇒ noop), `_pick_winner` tie behavior,
  ready-song candidate selection (skips current voteId, skips missing duration),
  task-id builders — and unit-test them. Transaction orchestration tested against a
  hand-rolled Firestore fake (no emulator in CI).
- WP-A/B/C agents write TDD tests for their new/changed code in their own worktrees;
  WP-E owns only the existing logic they don't touch, to avoid collisions.
- Minimal GitHub Actions workflow: on PR, `uv sync --all-packages` + `uv run pytest`
  across the workspace.

### WP-F — Docs & ADRs (review points 8, 9, undocumented tradeoffs)

- ADR: the Cloudflare Workers migration attempt (built, merged, removed in `62d70b2`)
  — context drafted from git history with marked prompts for Amit to fill in the
  actual rationale.
- ADRs / README updates for each decision changed above: polling replaces SSE (with
  the staleness bound), synchronous voting, spawn-based dispatch, Secret Manager
  tokens, signed URLs (with the WIF-dependency tradeoff), plus previously
  undocumented tradeoffs the review flagged.
- Runs **after** WP-A…E merge so the docs describe reality.

## Execution Plan

- WP-A through WP-E run as parallel agents in separate git worktrees; WP-F follows the
  merges.
- Known small overlaps: `terraform/cloud_run.tf` (different resource blocks),
  root `pyproject.toml` dev-deps, client vote/state code (WP-A hooks vs WP-B API
  routes vs WP-D track URL route). Merge order: A, then B, then C, D, E (rebase +
  resolve at merge time).
- Every agent: TDD, `uv run pytest` green, `terraform fmt` + `terraform validate`
  (init with `-backend=false`). **No `terraform apply`, no deploys, no package
  installs beyond the two approved dev deps.**
- Final verification after merges: full `pytest`, client `npm run build` + typecheck,
  `terraform validate`.

## Error Handling Principles (apply across WPs)

- Redis unavailable: vote-api returns 503 with actionable detail; `/state` returns the
  degraded snapshot with `redisAvailable: false` (existing behavior preserved).
- No silent catches: failures that change user-visible behavior are logged at ERROR
  with voteId context; benign degradations at WARNING.
- All new endpoints idempotent (scaledown, signed-URL minting).

## Testing Strategy Summary

| Area | Approach |
| --- | --- |
| Redis Lua (vote dedupe, poll init) | fakeredis[lua], behavioral tests |
| playback-service decision logic | pure-function unit tests |
| Firestore transaction orchestration | hand-rolled fake, unit tests |
| vote-api sync path | FastAPI TestClient + fakeredis |
| playback-stream /state caching | unit tests over cache staleness/dirty logic |
| modal-dispatch spawn/scaledown | unit tests with mocked modal SDK + fakeredis |
| Client polling hook | no test runner exists in `client/` (verified); gate on `tsc` typecheck + `next build`, keep hook logic in pure diffing functions for future tests |
| Infra | terraform fmt + validate in CI-less local runs |
