# PulseFM

AI-generated radio playback with real-time voting, polled state updates, and cloud-native orchestration on GCP.

## Problem / Motivation

PulseFM is built to run a continuous “station” where:

- songs are generated from poll outcomes,
- listeners vote in real time and get an authoritative result,
- playback rotates automatically,
- clients stay in sync by polling a cheap, cache-served `/state` snapshot.

The system prioritizes operational simplicity (Cloud Run + Cloud Functions + Redis + Firestore) and idempotent event processing over a monolithic backend.

## Architecture Overview

PulseFM is a monorepo with:

- a Next.js client (`client/`),
- Python Cloud Run services (`services/`),
- Python Cloud Functions (`functions/`),
- shared Python libs (`packages/`),
- Terraform infrastructure (`terraform/`).

```text
Browser (polls /api/playback/state every ~2s + jitter)
  -> Next.js (/client)
      -> vote-api (Cloud Run, OIDC)
      -> playback-stream (Cloud Run, polled GET /state)
      -> heartbeat-ingress (Cloud Function, OIDC)
      -> /api/track/{voteId} -> V4 signed GCS URLs (private bucket)

vote-api
  -> Redis (single atomic Lua call: validate + dedupe + tally)
  <- authoritative result (200 ok / 409 duplicate / 409 closed / 400 / 503)

playback-service (Cloud Run, scheduler via playback-queue)
  -> Firestore (stations, songs, voteState)
  -> Redis snapshot/tally init (atomic poll-open Lua), winnerOption on close
  -> Pub/Sub topic: vote-events (OPEN/CLOSE)
  -> Cloud Tasks (playback-queue: /tick + /vote/close)

playback-stream (Cloud Run)
  -> GET /state: short-TTL read-through caches over Redis (Firestore fallback)

encoder (Cloud Run, Eventarc GCS finalized on raw/*.wav)
  -> transcode wav->m4a (AAC 128k, 48k)
  -> write gs://pulsefm-generated-songs/encoded/{voteId}.m4a
  -> write Firestore songs/{voteId} (ready)

modal-dispatch-service (Cloud Run)
  <- Eventarc vote-events OPEN/CLOSE
  -> schedule warmup via modal-dispatch-queue
  -> spawn Modal worker generation (fire-and-forget)
  -> delayed /scaledown task: min_containers=0 + generation-failure logging
```

## Core Components

### Frontend + API gateway (`client/`)

- **Next.js 16** app with Auth.js JWT sessions.
- `proxy.ts` enforces auth on `/api/*` (except `/api/session`, `/api/auth/*`), injects `X-Session-Id`, and applies Upstash-based rate limits.
- Server routes proxy to backend services:
  - `/api/vote`
  - `/api/playback/state`
  - `/api/track/{voteId}` (mints cached V4 signed GCS URLs, see ADR 0006)
  - `/api/heartbeat`
  - `/api/session`, `/api/auth/*`
- Playback state is polled (`client/lib/pollDiff.ts` + `client/hooks/useStreamPlayer.ts`): every 2 s + 0–500 ms jitter, a boundary wake just after song `endAt`, and an immediate refetch after voting. UI transitions come from diffing consecutive snapshots.
- Uses Vercel OIDC + GCP Workload Identity Federation for keyless Cloud Run/Function invocation and GCS URL signing in production (`client/lib/server/cloud-run.ts`, `client/lib/server/gcs-signer.ts`).

### Vote API (`services/vote-api`)

- FastAPI endpoint `POST /vote`, synchronous and authoritative (ADR 0003).
- One atomic Redis Lua call (`SUBMIT_VOTE_LUA` in `packages/pulsefm-redis`) validates and tallies in a single round-trip: snapshot exists, `voteId` is current, poll is `OPEN`, option exists in the tally hash, session not already in the voted set — then `SADD` + `HINCRBY` only on first vote.
- The response is the result, not a promise:
  - `200 {"status":"ok"}` — vote counted
  - `409 Duplicate vote` / `409 Vote closed`
  - `400 Invalid voteId` / `400 Invalid option`
  - `503` — vote state unavailable or Redis unreachable (nothing was accepted)

### Playback Service (`services/playback-service`)

- FastAPI endpoints:
  - `POST /tick` (version-gated, idempotent/noop on stale version)
  - `POST /vote/close` (idempotent by `voteId` + `version`)
  - `POST /next/refresh`
- Responsibilities:
  - Rotate current/next song in Firestore transaction (`stations/main`, `songs/*`).
  - Close/open vote (`voteState/current`) on each tick.
  - Build/update Redis snapshot key `pulsefm:playback:current`; write `winnerOption` into the snapshot on vote close.
  - Initialize Redis snapshot/tally/voted keys for a new vote atomically (`POLL_OPEN_LUA`).
  - Publish `vote-events` OPEN/CLOSE and schedule next tasks.

### Playback Stream (`services/playback-stream`)

- Polled read API (ADR 0002): `GET /state` and `GET /health` — no SSE, no event ingest.
- `/state` serves the playback snapshot plus `poll.tallies`, `winnerOption`, `listeners`, and `redisAvailable` from short-TTL read-through caches: snapshot cached until the current song's `endAt`, tallies ~500 ms, listener count ~1 s.
- Per-instance cache skew between replicas is bounded by those TTLs (~0.5–2 s) — a deliberate tradeoff.
- Reads Redis first, Firestore fallback for snapshot reconstruction; degrades with `redisAvailable: false` when Redis is down.

### Encoder (`services/encoder`)

- CloudEvent HTTP handler (`POST /`) for GCS object finalized.
- Filters `raw/*.wav`, ignores files >100 MB.
- Uses `pydub` + `ffmpeg` to encode AAC `.m4a` at `128k` / `48k`.
- Writes encoded object metadata cache-control and creates `songs/{voteId}` with `durationMs`, `status=ready`, `createdAt=SERVER_TIMESTAMP`.

### Modal Dispatch Service (`services/modal-dispatch-service`)

- Handles vote events (ADR 0004):
  - `OPEN`: schedule `/warmup` at `endAt - 30s` if active listeners.
  - `CLOSE`: idempotent by `voteId`; scale Modal min instances to 1, `.spawn()` generation fire-and-forget (call id stored in Redis), then enqueue a delayed `POST /scaledown` Cloud Task (`modal-scaledown-{voteId}`, delay = `GENERATION_HORIZON_SECONDS`).
  - `/scaledown`: idempotent; sets min instances back to 0 with retries and logs ERROR if the spawned generation failed (rotation falls back to the stubbed song).
- Uses Redis heartbeat active key for listener-aware behavior.
- Modal tokens are injected from Secret Manager, not plaintext env vars (ADR 0005).

### Modal Worker (`services/worker`)

- Modal app (`pulsefm-worker`) that generates WAV and uploads to `raw/{voteId}.wav`.
- Uses descriptor mapping (`packages/pulsefm-descriptors`) through dispatch service.

### Heartbeat Functions

- `heartbeat-ingress` (HTTP): publish heartbeat event with `sessionId`.
- `heartbeat-receiver` (Pub/Sub trigger): atomically refresh:
  - `pulsefm:heartbeat:active`
  - `pulsefm:heartbeat:session:{sessionId}` (TTL 30s)

### Next Song Updater (`functions/next-song-updater`)

- Triggered on encoded object finalize events.
- Enqueues `/next/refresh` task (idempotent task id per voteId) on `playback-queue`.

## Tech Stack

- **Languages**: TypeScript (client), Python 3.11/3.12 (services/functions/worker), HCL (Terraform).
- **Frontend**: Next.js 16, React 19, Auth.js, Upstash Redis.
- **Backend runtime**: FastAPI + Uvicorn (Cloud Run), Functions Framework (Cloud Functions Gen2).
- **Infra**: Cloud Run, Cloud Functions Gen2, Firestore Native, Pub/Sub, Cloud Tasks, Eventarc, Memorystore Redis, GCS, Artifact Registry, Secret Manager.
- **Packaging**: UV workspace (`pyproject.toml` at repo root).
- **CI/CD**: Cloud Build pipeline (`cloudbuild/deploy.yaml`) + Terraform apply + image build/push + Cloud Run deploy.

## Key Design Decisions

Architecture decision records live in `docs/adr/`.

1. **Redis is canonical for live poll tallies/dedupe**
   - Why: low-latency atomic increments and reads.
   - Tradeoff: Redis outage disables voting (503) until it recovers; playback keeps running via Firestore fallback.

2. **Client polling instead of SSE** ([ADR 0002](docs/adr/0002-polling-over-sse.md))
   - Why: SSE busy-polled per connection, pinned a Cloud Run concurrency slot per listener, and kept per-instance event state that replicas disagreed on.
   - Tradeoff: tallies are up to ~2 s stale; changeover stays tight via a poll scheduled at the song boundary.

3. **Synchronous, authoritative vote tally** ([ADR 0003](docs/adr/0003-synchronous-vote-tally.md))
   - Why: the async Cloud Tasks path returned 200 before the authoritative dedupe — votes could silently fail to count.
   - Tradeoff: loses queue spike-buffering; the single Lua call is O(1) and the real ceilings are far beyond hobby scale.

4. **Version-gated `/tick` and idempotent close**
   - Why: tolerate retries and out-of-order task delivery.
   - Tradeoff: requires strict version propagation from scheduler/tasks.

5. **Firestore keeps playback/vote state; Redis caches live snapshot**
   - Why: durable control-plane state + fast read path.
   - Tradeoff: dual-write paths require reconciliation logic.

6. **Pub/Sub + Eventarc for vote lifecycle events**
   - Why: decouples playback orchestration from Modal dispatch.
   - Tradeoff: at-least-once delivery; the consumer is idempotent by `voteId`. Only the `vote-events` topic remains — the `tally` and `playback` topics were deleted with their consumers (ADRs 0002/0003).

7. **OIDC keyless server-to-server auth from Vercel**
   - Why: avoids static service account keys for Next.js backend.
   - Tradeoff: WIF configuration complexity and IAM dependencies.

8. **Modal dispatch separated from playback orchestration** ([ADR 0004](docs/adr/0004-modal-spawn-dispatch.md))
   - Why: isolates GPU generation and the warmup/scale-down lifecycle; `.spawn()` + a delayed scale-down task means no webhook ever blocks on generation.
   - Tradeoff: extra service and queue to operate; generation failures surface as ERROR logs, not request errors.

## Tradeoffs & Limitations

- Tally freshness is bounded by the poll interval (~2 s + jitter) plus the server-side tally cache (≤500 ms).
- Playback-stream replicas may briefly disagree: per-instance cache skew is bounded by the cache TTLs (~0.5–2 s).
- Playback-stream listener counting scans Redis keys; cost/perf depends on key cardinality.
- Signed track URLs have unique query strings, which defeat shared HTTP caches — GCS egress grows with listener count ([ADR 0006](docs/adr/0006-signed-urls-for-audio.md)). First thing to revisit if scale outweighs privacy.
- Memorystore basic tier: tallies/dedupe are lost on failover; users may re-vote once (accepted).

## Getting Started (Local Dev)

### Prerequisites

- Python 3.11+ and `uv`
- Node.js 20+ (for Next.js)
- Docker (optional, for service-specific compose)
- Access to GCP resources if running against cloud dependencies

### Install dependencies

```bash
# Python workspace
uv sync --all-packages

# Client
cd client
npm install
```

### Key environment variables

#### Client (`client/.env.local`)

| Variable                                 | Required           | Notes                             |
| ---------------------------------------- | ------------------ | --------------------------------- |
| `AUTH_SECRET` or `NEXTAUTH_SECRET`       | yes                | Auth.js JWT secret                |
| `VOTE_API_URL`                           | yes                | Cloud Run URL for vote-api        |
| `HEARTBEAT_INGRESS_URL`                  | yes                | Cloud Function URL                |
| `PLAYBACK_STREAM_URL`                    | yes                | Cloud Run URL for playback-stream |
| `UPSTASH_REDIS_REST_URL`                 | yes (for proxy RL) | Upstash endpoint                  |
| `UPSTASH_REDIS_REST_TOKEN`               | yes (for proxy RL) | Upstash token                     |
| `GCP_PROJECT_ID`                         | prod OIDC          | Vercel OIDC flow                  |
| `GCP_PROJECT_NUMBER`                     | prod OIDC          | Vercel OIDC flow                  |
| `GCP_SERVICE_ACCOUNT_EMAIL`              | prod OIDC          | usually `nextjs-server@...`       |
| `GCP_WORKLOAD_IDENTITY_POOL_ID`          | prod OIDC          | Terraform output                  |
| `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID` | prod OIDC          | Terraform output                  |
| `GCS_SONGS_BUCKET`                       | optional           | signed-URL bucket (default `pulsefm-generated-songs`) |
| `GCS_SONGS_PREFIX`                       | optional           | signed-URL object prefix (default `encoded/`) |

Audio is resolved through `/api/track/{voteId}` signed URLs; there is no public bucket/CDN base URL.

#### Core service envs

- `vote-api`: `REDIS_HOST`, `REDIS_PORT`
- `playback-service`: `PROJECT_ID`, `LOCATION`, `PLAYBACK_TICK_URL`, `PLAYBACK_QUEUE_NAME`, `VOTE_EVENTS_TOPIC`, Firestore collection names, Redis host/port
- `playback-stream`: `REDIS_HOST`, `REDIS_PORT`, Firestore collection names
- `encoder`: bucket/prefix vars, Redis host/port
- `modal-dispatch-service`: `MODAL_QUEUE_NAME`, `MODAL_DISPATCH_SERVICE_URL`, `GENERATION_HORIZON_SECONDS`, warmup/scale-down tuning vars, Redis host/port; `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` are injected from Secret Manager via `secret_key_ref` (ADR 0005), not set by hand

### Run locally

#### Client

```bash
cd client
npm run dev
```

#### Individual services via Docker Compose

```bash
docker compose -f services/vote-api/docker-compose.yml up --build
docker compose -f services/playback-service/docker-compose.yml up --build
docker compose -f services/playback-stream/docker-compose.yml up --build
docker compose -f services/encoder/docker-compose.yml up --build
docker compose -f services/modal-dispatch-service/docker-compose.yml up --build
```

Default local port mappings:

- vote-api `8090`
- encoder `8081`
- playback-stream `8092`
- playback-service `8094`
- modal-dispatch-service `8084`

## Testing

Python suites (behavioral tests run Lua against `fakeredis[lua]` — including the poll-open atomics and the voted-set TTL sentinel):

- `packages/pulsefm-redis/tests` — `SUBMIT_VOTE_LUA` / `POLL_OPEN_LUA` behavior, snapshot helpers
- `packages/pulsefm-auth/tests` — session handling
- `services/vote-api/tests` — synchronous vote endpoint contract
- `services/playback-service/tests` — rotation decision logic, close-vote orchestration
- `services/playback-stream/tests` — `/state` caching and staleness
- `services/modal-dispatch-service/tests` — close-event spawn path, `/scaledown`

Run everything:

```bash
uv run pytest packages/ services/
```

CI (`.github/workflows/ci.yml`) runs `uv sync --all-packages` + the same pytest invocation on PRs and pushes to main. The client has no test runner; it is gated by `tsc` typecheck and `next build`, with polling/diff logic kept in pure functions (`client/lib/pollDiff.ts`) for future tests. There is no integration/e2e suite for the multi-service flow.

## API / Interfaces

### Vote API (Cloud Run)

- `POST /vote`
- `GET /health`

Example:

```bash
curl -X POST "$VOTE_API_URL/vote" \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: <session-id>" \
  -d '{"voteId":"<vote-id>","option":"<option>"}'
```

### Playback Service (Cloud Run)

- `POST /tick` body: `{"version": <int>}`
- `POST /vote/close` body: `{"voteId":"...","version":<int>}`
- `POST /next/refresh` body: `{"voteId":"..."}`
- `GET /health`

### Playback Stream (Cloud Run)

- `GET /state`
- `GET /health`

### Modal Dispatch Service (Cloud Run)

- `POST /events/vote` (Eventarc target, OPEN/CLOSE)
- `POST /warmup`, `POST /scaledown` (Cloud Tasks targets)
- `GET /health`

### Cloud Functions

- `heartbeat-ingress` (HTTP)
- `heartbeat-receiver` (Pub/Sub event)
- `next-song-updater` (GCS finalized event)

## Deployment

### Terraform

```bash
cd terraform
terraform init
terraform apply
```

Remote state backend is configured to GCS bucket `pulsefm-terraform-state` (`terraform/backend.tf`).

The `pulsefm-generated-songs` bucket is private; audio is delivered via V4 signed URLs minted by the Next.js server ([ADR 0006](docs/adr/0006-signed-urls-for-audio.md)).

### Cloud Build pipeline

`cloudbuild/deploy.yaml` performs:

1. `terraform apply` (with SA impersonation),
2. build & push service images to Artifact Registry,
3. deploy Cloud Run services.

Cloud Build trigger management is intentionally outside Terraform.

### Cloudflare migration (historical)

A Cloudflare Workers backend migration was attempted and abandoned in March 2026; no Cloudflare code remains in the repo. See [ADR 0001](docs/adr/0001-cloudflare-migration-attempt.md) for the history.

### Bootstrap image script

For first deploy/bootstrap tags:

```bash
./scripts/build_push_bootstrap_images.sh
```

## Observability

- Structured-ish application logging across all services/functions via Python `logging`.
- Health endpoints:
  - `/health` on Cloud Run services.
- No metrics/tracing stack configured in repo (no Prometheus/OpenTelemetry setup).

## Security Notes

- Next.js API auth uses Auth.js JWT cookie; session id is derived from JWT `sub`.
- Next.js -> Cloud Run/Function calls use OIDC:
  - local: ADC ID token client,
  - production: Vercel OIDC + GCP WIF + IAM Credentials generateIdToken.
- Cloud Run invoker IAM is scoped (not all public) except `playback-stream` which is intentionally public.
- GCS `pulsefm-generated-songs` is private (no `allUsers` binding). Audio is served via session-gated V4 signed URLs minted with IAM `signBlob` over WIF ([ADR 0006](docs/adr/0006-signed-urls-for-audio.md)).
- Modal tokens live in Secret Manager with a scoped `secretAccessor` binding, consumed via `secret_key_ref` ([ADR 0005](docs/adr/0005-secret-manager-for-modal-tokens.md)); note the residual risk that Terraform-managed secret versions persist in TF state.
- `terraform.tfvars` and local credentials are excluded from version control in your workflow.

## Future Improvements

1. Add a CDN with signed cookies/tokens in front of `pulsefm-generated-songs/encoded/*` if egress from unique signed URLs becomes a cost problem (ADR 0006's revisit point).
2. Add load tests for `/state` polling fan-out and Redis hot-key behavior.
3. Replace Redis `SCAN`-based listener counting with a cardinality-friendly pattern.
4. Add DLQ/replay strategy for the remaining queues (`playback-queue`, `modal-dispatch-queue`) and Eventarc deliveries.
5. Add explicit schema validation for Pub/Sub payloads across services.
6. Add OpenAPI docs and contract tests for internal endpoints.
7. Extend CI with lint/typecheck and a client build gate (Python tests already run on PRs).
8. Add secret scanning + policy checks in CI.
9. Add vote history persistence sink if analytics/auditing is required.
10. Add dashboards/alerts for Redis errors, task retry spikes, and Eventarc delivery failures.
