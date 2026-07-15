# 0001. Cloudflare Workers Migration Attempt

Date: 2026-07-15
Status: Recorded — historical

## Context

Between 2026-03-06 and 2026-03-11 the project explored migrating the GCP backend to
Cloudflare Workers. The history below is reconstructed from git; the rationale blocks
are left for the author to fill in.

**Phase 1 — scaffolding (merged to main, later removed).**

- `b6c9346` (2026-03-06) "chore(cloudflare): add backend migration boilerplate
  scaffolding" added a non-deploying, resource-free slice: `infra/cloudflare/`
  (`wrangler.toml`, per-service secrets examples for vote-api, playback-service,
  playback-stream, encoder, and modal-dispatch-service), `scripts/cloudflare/`
  (`validate.sh`, `whoami.sh`), `docs/cloudflare/` (README plus a
  `PHASE2_BACKEND_MIGRATION.md` outline), and two GitHub workflows
  (`cloudflare-validate.yml`, `cloudflare-deploy.yml`).
- `7e5185d` documented the scaffold in the README and gitignored local wrangler state.
- `17073d6` merged the above to main via PR #2
  (`feat/cloudflare-backend-boilerplate`).

**Phase 2 — playback-worker prototype (never merged to main).**

On side branches (`feat/playback-worker-durable-object-migration`,
`feat/playback-worker-simple-do-loop`, `refactor/v2`):

- `f9ecafa` (2026-03-06) "feat(playback-worker): add Python Worker + Durable Object +
  D1 playback runtime" — a `services/playback-worker` slice with a ~450-line
  `src/entry.py` and a D1 migration (`migrations/d1/0001_init.sql`), intended to
  replace the playback orchestration path.
- Iterations followed: `d117bbf` made orchestration alarm-driven with a state-only
  API, `7bc7a31` renamed tick transitions to `next_song` events, `e725bbb` removed
  startup-orchestration integration, `974150d`/`01375ed` updated the migration docs.
- `55e5970` (2026-03-10) "Project restructure for cloudflare workers backend"
  restructured the whole repo into an `apps/` layout (`services/encoder` →
  `apps/encoder`, `client` → `apps/web`, playback-worker with an orchestrator module
  and `tests/test_orchestrator.py`).

**Removal.**

- `62d70b2` (2026-03-11) "Remove cloudflare artifacts" deleted all phase-1
  scaffolding from main (the phase-2 work had never landed there). No Cloudflare
  code remains in the repository; the backend stayed on GCP (Cloud Run, Cloud
  Functions, Firestore, Memorystore, Pub/Sub, Cloud Tasks).

> **[AMIT: fill in — why was the migration attempted? What did Workers/D1/Durable
> Objects promise over the Cloud Run stack (cost, latency, operational simplicity,
> curiosity)?]**

## Decision

The migration was abandoned; PulseFM remains on GCP. The scaffolding was removed
from main in `62d70b2` and the prototype branches were left unmerged.

> **[AMIT: fill in — why was the migration abandoned? What blocked or de-motivated
> it (Python Workers maturity, Durable Object fit for the playback loop, D1 limits,
> effort vs. benefit, something else)?]**

## Consequences

- The GCP architecture documented in the README and in ADRs 0002–0006 is the real,
  maintained system; hardening effort went there instead of into a platform move.
- The playback-worker prototype (Durable Object + D1 + alarm-driven orchestration)
  exists only on unmerged branches. Anyone revisiting a Cloudflare move should start
  from those branches and this ADR rather than from scratch.
- The repo briefly carried an `apps/` restructure on `refactor/v2`; main never
  adopted it, so paths in old branch commits do not match main's layout.
