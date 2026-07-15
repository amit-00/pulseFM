# WP-F: Docs & ADRs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document every hardening decision as ADRs, update the README to describe the post-hardening system, and record the Cloudflare migration history.

**Architecture:** Standard lightweight ADRs (`docs/adr/NNNN-title.md`, Status/Context/Decision/Consequences). README sections rewritten to match merged reality — this WP runs LAST, after WP-A…E are merged, and every claim must be verified against the code as merged, not against the plans.

**Tech Stack:** Markdown only. No code changes.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-F section).
- SEQUENCING: run only after WP-A…E are merged into the working branch. Verify first: `grep -rn "/stream" services/playback-stream/` must be empty and `services/vote-api/pulsefm_vote_api/main.py` must contain `submit_vote_atomic` — if not, STOP and report that prerequisites aren't merged.
- Every factual claim in the docs must be checked against the merged code (grep/read before writing). Do not describe planned behavior that didn't land.
- The Cloudflare ADR requires the author's rationale. Draft context from git history (`git log --all --oneline -- 'infra/cloudflare*' 'docs/cloudflare*'`, commits `b6c9346`, `7e5185d`, `17073d6`, `62d70b2`) and mark the decision rationale with `> **[AMIT: fill in — why was the migration attempted, and why abandoned?]**` blocks. Do not invent reasons.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: ADRs

**Files:**
- Create: `docs/adr/0001-cloudflare-migration-attempt.md`
- Create: `docs/adr/0002-polling-over-sse.md`
- Create: `docs/adr/0003-synchronous-vote-tally.md`
- Create: `docs/adr/0004-modal-spawn-dispatch.md`
- Create: `docs/adr/0005-secret-manager-for-modal-tokens.md`
- Create: `docs/adr/0006-signed-urls-for-audio.md`

Each ADR uses this shape:

```markdown
# NNNN. <Title>

Date: 2026-07-15
Status: Accepted (0001: Recorded — historical)

## Context
<what was true before, with file/commit references>

## Decision
<what we do now>

## Consequences
<positive, negative, accepted risks — be honest>
```

Required content per ADR (verify each against merged code):

- **0001** — history of the Cloudflare backend slice (built in `b6c9346`/`7e5185d`, merged in `17073d6`, removed in `62d70b2`); what the slice contained (Python Worker, Durable Object, D1, playback-worker orchestrator with tests — from the commit diffs); rationale blocks marked for Amit as described in Global Constraints.
- **0002** — SSE on Cloud Run (50 ms busy-poll, per-instance `StreamState`, per-listener concurrency slots) → polling `/state` every ~2 s with jitter + snapshot diffing. Consequences: ~2 s tally staleness (bounded per-instance cache skew documented), no long-lived connections, `winnerOption` now travels via the Redis snapshot; the dead `playback` topic and Eventarc triggers were removed; `vote-events` topic retained for modal-dispatch.
- **0003** — async Cloud Tasks tally (200-before-tally, silent failure) → `SUBMIT_VOTE_LUA` single-round-trip authoritative voting in vote-api; tally-function/queue/topic deleted. Consequences: honest client results (409 duplicate/closed), Redis outage now returns 503 instead of silently accepting, spike-buffering queue lost (accepted at current scale).
- **0004** — blocking `.remote()` inside an Eventarc webhook → `.spawn()` + delayed idempotent `/scaledown` Cloud Task that also logs generation failures. Consequences: no stranded `min_containers=1`, failure signal moved from request errors to ERROR logs, stubbed-song fallback covers failed generations.
- **0005** — plaintext env tokens → Secret Manager + `secret_key_ref` (pattern parity with `nextjs_session_signing_key`). Note the residual risk honestly: secret *versions* managed by Terraform still exist in TF state; state bucket access is the real boundary.
- **0006** — public `allUsers` bucket → session-gated `/api/track/{voteId}` minting cached V4 signed URLs via IAM `signBlob` over WIF. Consequences: audio depends on the WIF/IAM chain (mitigated by 1 h URLs + server/client caches + stale-if-error), unique query strings defeat shared HTTP caches (higher egress at scale), first WP to revisit if scale outweighs privacy.

- [ ] **Step 1:** Write all six ADRs, verifying claims against code (e.g. confirm the Lua script name, the `/scaledown` task id, the actual timeout values in `terraform/cloud_run.tf`).
- [ ] **Step 2:** Commit — `docs(adr): record hardening decisions and cloudflare migration history`

---

### Task 2: README rewrite for merged reality

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Update these sections to match merged code (verify each):
- **Architecture Overview diagram:** remove tally-function/tally-queue, SSE arrows, and the playback topic; show vote-api → Redis (atomic Lua) directly; playback-stream serves `GET /state` (polled); modal-dispatch `/scaledown` via delayed task; Next.js `/api/track/{voteId}` → signed GCS URLs.
- **Core Components:** rewrite Vote API (authoritative sync result contract with the exact status codes), Playback Stream (polled read API, cache staleness bounds ~0.5–2 s), Modal Dispatch (spawn + scaledown), delete the Tally Function subsection.
- **Key Design Decisions:** add polling-over-SSE and synchronous-tally entries pointing at ADRs 0002/0003; fix entry 4 (Pub/Sub fan-out) to reflect that only `vote-events` remains.
- **Tradeoffs & Limitations:** replace the public-URL line with the signed-URL tradeoff; add per-instance cache skew bound; keep the Redis SCAN listener-counting line.
- **Testing:** list the real suites (`packages/pulsefm-redis/tests`, `packages/pulsefm-auth/tests`, `services/vote-api/tests`, `services/playback-service/tests`, `services/playback-stream/tests`, `services/modal-dispatch-service/tests`) and the CI workflow.
- **Environment tables:** vote-api envs (drop `TALLY_FUNCTION_URL`/`VOTE_QUEUE_NAME`), modal-dispatch (`GENERATION_HORIZON_SECONDS`, tokens now via Secret Manager), client (drop `NEXT_PUBLIC_BUCKET_BASE_URL`/`NEXT_PUBLIC_CDN_BASE_URL`, note `GCS_SONGS_BUCKET`/`GCS_SONGS_PREFIX`).
- **Security Notes:** bucket is private; signed URLs; Modal tokens in Secret Manager.
- **Future Improvements:** remove items now done (DLQ item stays relevant only for playback-queue/modal queue — reword; CDN item stays; secret-scanning item stays).
- **Cloudflare section:** replace the stale "phase 1 scaffolding is available" paragraph (those paths no longer exist) with one line pointing at ADR 0001.

- [ ] **Step 2:** Verify no stale references: `grep -n "tally-function\|/stream\|NEXT_PUBLIC_BUCKET\|storage.googleapis.com" README.md` — expect no hits (except in historical ADR-pointer context if any).
- [ ] **Step 3:** Commit — `docs(readme): describe post-hardening architecture`
