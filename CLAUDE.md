# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PulseFM is a multi-cloud internet radio station where listeners vote on the next AI-generated song. It spans three runtime environments: a Next.js static frontend, a Cloudflare Worker + Durable Object backend, and a Modal GPU service for music generation.

## Commands

### Client (Next.js) — managed with Bun

```bash
cd client
bun install
bun run dev          # Local dev server
bun run build        # Static export → client/out/
bun x eslint         # Lint
```

### Cloudflare Worker — managed with npm

```bash
cd cloudflare
npm install
npm run check                                        # TypeScript validation (tsc --noEmit)
npm run deploy                                       # Deploy to production
npm run deploy:preview                               # Deploy to preview environment
npm run migrate                                      # Apply D1 migrations
node scripts/render-config.mjs wrangler.jsonc        # Render wrangler.jsonc from template
```

### Modal Generator — managed with UV/pip

```bash
cd modal
pip install -e .
modal deploy pulsefm_worker/app.py    # Deploy GPU service
python -m py_compile pulsefm_worker/app.py  # Syntax check
```

## Architecture

### High-Level Data Flow

1. Client polls `GET /api/state` every 3s
2. Users vote via `POST /api/vote` with a session token (HMAC-SHA256, stored in localStorage)
3. When a poll closes, the winning descriptor triggers `GenerateSongWorkflow`
4. The Cloudflare Workflow calls Modal's `POST /jobs` endpoint (GPU, ACE-Step model, ~150s audio)
5. Modal uploads encoded M4A to R2, then POSTs back to `/internal/callback`
6. Client streams audio from R2 via HTML5 audio element

### Runtime Layers

| Layer | Tech | Role |
|-------|------|------|
| Frontend | Next.js + React (static export) | Polling, voting, audio playback |
| API Gateway | Cloudflare Worker | HTTP routing, session validation, CORS |
| State Machine | StationControl Durable Object | Single writer for all station state |
| Orchestration | Cloudflare Workflows | Async generation job with 15min timeout |
| Database | D1 (SQLite) | Songs, poll rounds, generation jobs |
| Object Storage | R2 | Audio artifacts |
| GPU Compute | Modal (ACE-Step) | Music generation, encoding, R2 upload |

### Single-Writer Invariant

`StationControl` (Durable Object) is the **only** writer for: playback state, poll options/tallies, vote deduplication, listener presence, and scheduled events. All other Worker endpoints are read-only or delegate mutations into the DO.

### Key Source Files

**Cloudflare (`cloudflare/src/`)**
- `index.ts` — HTTP routing; public `/api/*` and internal `/internal/*` routes
- `station-control.ts` — Durable Object state machine (playback, polls, presence)
- `workflow.ts` — `GenerateSongWorkflow`: calls Modal, waits for callback, handles timeout
- `session.ts` — HMAC-SHA256 token issuance and verification
- `db.ts` — D1 queries for songs, poll rounds, generation job tracking
- `options.ts` — 48 pre-defined descriptor tuples (genre/mood/energy)
- `types.ts` — Shared TypeScript interfaces

**Client (`client/`)**
- `components/SynthesizerPlayer.tsx` — Main orchestrator: polling loop, UI state
- `hooks/useStreamPlayer.ts` — Audio element lifecycle, playback logic
- `lib/stream.ts` — API calls: session bootstrap, state polling, vote submission

**Modal (`modal/pulsefm_worker/`)**
- `app.py` — FastAPI endpoints + GPU task definitions; accepts descriptor, generates audio, uploads to R2, callbacks Cloudflare

### Configuration

`wrangler.template.jsonc` is the source of truth for the Cloudflare Worker config. It is rendered to `wrangler.jsonc` before deployment via `node scripts/render-config.mjs wrangler.jsonc`. Never edit `wrangler.jsonc` directly.

Runtime secrets and deploy-time config are injected via environment variables (GitHub Actions) or a local `.env` file (git-ignored). See `wrangler.template.jsonc` and `modal/README.md` for required variable names.

### Database Schema

Three tables in D1 (`cloudflare/migrations/`):
- `songs` — status, R2 key, public URL, winning descriptor, timestamps
- `poll_rounds` — vote_id, opened/closed timestamps, winner
- `generation_jobs` — workflow instance ID, external job ID, retry count, failure reason

### CI/CD

- **`ci.yml`** — Runs on PR and main push: ESLint, Next.js build, Cloudflare tsc, Modal syntax check
- **`deploy.yml`** — Runs on main push: renders wrangler config, migrates D1, deploys Worker + Pages
- **`modal-deploy.yml`** — Runs when `modal/` changes: deploys Modal app
