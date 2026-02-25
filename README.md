# PulseFM

AI-generated radio playback with real-time voting, streaming state updates, and cloud-native orchestration on GCP.

## Problem / Motivation

PulseFM is built to run a continuous “station” where:

- songs are generated from poll outcomes,
- listeners vote in real time,
- playback rotates automatically,
- clients receive low-latency state/tally updates without polling.

The system prioritizes operational simplicity (Cloud Run + Cloud Functions + Redis + Firestore) and idempotent event processing over a monolithic backend.

## Architecture Overview

PulseFM is a monorepo with:

- a Next.js client (`client/`),
- Python Cloud Run services (`services/`),
- Python Cloud Functions (`functions/`),
- shared Python libs (`packages/`),
- Terraform infrastructure (`terraform/`).

```text
Browser
  -> Next.js (/client)
      -> vote-api (Cloud Run, OIDC)
      -> playback-stream (Cloud Run, SSE proxy)
      -> heartbeat-ingress (Cloud Function, OIDC)

vote-api
  -> Cloud Tasks (tally-queue)
      -> tally-function (Cloud Function HTTP)
          -> Redis tally/voted keys
          -> Pub/Sub topic: tally

playback-service (Cloud Run, scheduler via playback-queue)
  -> Firestore (stations, songs, voteState)
  -> Redis snapshot/tally init
  -> Pub/Sub topics: playback, vote-events
  -> Cloud Tasks (playback-queue: /tick + /vote/close)

playback-stream (Cloud Run)
  <- Eventarc (Pub/Sub -> /events/tally, /events/playback, /events/vote)
  -> SSE to clients (/stream), snapshot API (/state)

encoder (Cloud Run, Eventarc GCS finalized on raw/*.wav)
  -> transcode wav->m4a (AAC 128k, 48k)
  -> write gs://pulsefm-generated-songs/encoded/{voteId}.m4a
  -> write Firestore songs/{voteId} (ready)

modal-dispatch-service (Cloud Run)
  <- Eventarc vote-events OPEN/CLOSE
  -> schedule warmup via modal-dispatch-queue
  -> invoke Modal worker generation
```

## Core Components

### Frontend + API gateway (`client/`)

- **Next.js 16** app with Auth.js JWT sessions.
- `proxy.ts` enforces auth on `/api/*` (except `/api/session`, `/api/auth/*`), injects `X-Session-Id`, and applies Upstash-based rate limits.
- Server routes proxy to backend services:
  - `/api/vote`
  - `/api/playback/state`
  - `/api/playback/stream`
  - `/api/heartbeat`
  - `/api/session`, `/api/auth/*`
- Uses Vercel OIDC + GCP Workload Identity Federation for keyless Cloud Run/Function invocation in production (`client/lib/server/cloud-run.ts`).

### Vote API (`services/vote-api`)

- FastAPI endpoint `POST /vote`.
- Validates:
  - `X-Session-Id` exists,
  - `voteId` matches current poll in Redis snapshot,
  - poll is `OPEN`,
  - option exists in Redis tally hash,
  - session not already in voted set.
- Enqueues tally task to `tally-queue` targeting `tally-function`.

### Tally Function (`functions/tally-function`)

- HTTP Cloud Function called by Cloud Tasks.
- Atomic dedupe + tally increment via Redis Lua script:
  - `SADD pulsefm:poll:{voteId}:voted`
  - `HINCRBY pulsefm:poll:{voteId}:tally {option} 1` only if first vote
- Publishes `{voteId}` to Pub/Sub topic `tally`.

### Playback Service (`services/playback-service`)

- FastAPI endpoints:
  - `POST /tick` (version-gated, idempotent/noop on stale version)
  - `POST /vote/close` (idempotent by `voteId` + `version`)
  - `POST /next/refresh`
- Responsibilities:
  - Rotate current/next song in Firestore transaction (`stations/main`, `songs/*`).
  - Close/open vote (`voteState/current`) on each tick.
  - Build/update Redis snapshot key `pulsefm:playback:current`.
  - Initialize Redis tally/voted keys for new vote atomically.
  - Publish vote/playback events and schedule next tasks.

### Playback Stream (`services/playback-stream`)

- FastAPI endpoints:
  - `GET /state`
  - `GET /stream` (SSE)
  - `POST /events/tally`, `/events/playback`, `/events/vote` (Eventarc targets)
- Emits SSE events:
  - `HELLO`
  - `TALLY_SNAPSHOT`
  - `TALLY_DELTA`
  - `SONG_CHANGED`
  - `NEXT-SONG-CHANGED`
  - `VOTE_CLOSED`
  - `HEARTBEAT`
- Reads Redis first, Firestore fallback for snapshot reconstruction.

### Encoder (`services/encoder`)

- CloudEvent HTTP handler (`POST /`) for GCS object finalized.
- Filters `raw/*.wav`, ignores files >100 MB.
- Uses `pydub` + `ffmpeg` to encode AAC `.m4a` at `128k` / `48k`.
- Writes encoded object metadata cache-control and creates `songs/{voteId}` with `durationMs`, `status=ready`, `createdAt=SERVER_TIMESTAMP`.

### Modal Dispatch Service (`services/modal-dispatch-service`)

- Handles vote events:
  - `OPEN`: schedule `/warmup` at `endAt - 30s` if active listeners.
  - `CLOSE`: idempotent by `voteId`, scale Modal min instances to 1, dispatch generation, scale back to 0 with retry horizon.
- Uses Redis heartbeat active key for listener-aware behavior.

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

1. **Redis is canonical for live poll tallies/dedupe**
   - Why: low-latency increments and reads.
   - Tradeoff: Redis outage blocks voting/tally updates.

2. **Version-gated `/tick` and idempotent close**
   - Why: tolerate retries and out-of-order task delivery.
   - Tradeoff: requires strict version propagation from scheduler/tasks.

3. **Firestore keeps playback/vote state; Redis caches live snapshot**
   - Why: durable control-plane state + fast read path.
   - Tradeoff: dual-write paths require reconciliation logic.

4. **Pub/Sub + Eventarc fan-out for stream/reactive updates**
   - Why: decouples producers from stream consumers.
   - Tradeoff: event ordering is not strict; client/state reconciliation needed.

5. **OIDC keyless server-to-server auth from Vercel**
   - Why: avoids static service account keys for Next.js backend.
   - Tradeoff: WIF configuration complexity and IAM dependencies.

6. **Modal dispatch separated from playback orchestration**
   - Why: isolates long-running generation and warmup lifecycle.
   - Tradeoff: extra service and queue to operate.

## Tradeoffs & Limitations

- Playback-stream listener counting scans Redis keys; cost/perf depends on key cardinality.
- Minimal automated test coverage in current repo.
- Media is currently served from public GCS object URLs (no CDN edge cache).

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
| `NEXT_PUBLIC_CDN_BASE_URL`               | optional           | e.g. `https://cdn.pulsefm.fm`     |
| `NEXT_PUBLIC_BUCKET_BASE_URL`            | optional           | fallback base URL                 |

#### Core service envs

- `vote-api`: `PROJECT_ID`, `LOCATION`, `VOTE_QUEUE_NAME`, `TALLY_FUNCTION_URL`, `REDIS_HOST`, `REDIS_PORT`
- `playback-service`: `PROJECT_ID`, `LOCATION`, `PLAYBACK_TICK_URL`, `PLAYBACK_QUEUE_NAME`, topic names, Firestore collection names, Redis host/port
- `playback-stream`: `REDIS_HOST`, `REDIS_PORT`, stream interval vars
- `encoder`: bucket/prefix vars, Redis host/port
- `modal-dispatch-service`: modal token vars, queue URL/name, Redis host/port

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

Current automated tests are minimal:

- `packages/pulsefm-auth/tests/test_session.py`

Run:

```bash
uv run pytest packages/pulsefm-auth/tests
```

There is no comprehensive integration/e2e test suite in-repo for the multi-service flow.

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
- `GET /stream` (SSE)
- Event ingest endpoints for Eventarc:
  - `POST /events/tally`
  - `POST /events/playback`
  - `POST /events/vote`
- `GET /health`

### Cloud Functions

- `tally-function` (HTTP)
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

Audio delivery currently uses direct public object URLs from `pulsefm-generated-songs`.

### Cloud Build pipeline

`cloudbuild/deploy.yaml` performs:

1. `terraform apply` (with SA impersonation),
2. build & push service images to Artifact Registry,
3. deploy Cloud Run services.

Cloud Build trigger management is intentionally outside Terraform.

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
- GCS `pulsefm-generated-songs` currently grants `roles/storage.objectViewer` to `allUsers` at bucket level (public reads).
- `terraform.tfvars` and local credentials are excluded from version control in your workflow.

## Future Improvements

1. Add Cloud CDN in front of `pulsefm-generated-songs/encoded/*` to reduce global latency, improve cache hit ratios for hot tracks, and offload bucket egress bursts.
2. Add load tests for SSE fanout and Redis hot-key behavior.
3. Replace Redis `SCAN`-based listener counting with a cardinality-friendly pattern.
4. Add DLQ/replay strategy for task/event failures.
5. Add explicit schema validation for Pub/Sub payloads across services.
6. Add OpenAPI docs and contract tests for internal endpoints.
7. Add CI workflow (lint/test/typecheck/build) before Cloud Build deploy.
8. Add secret scanning + policy checks in CI.
9. Add vote history persistence sink if analytics/auditing is required.
10. Add dashboards/alerts for Redis errors, task retry spikes, and Eventarc delivery failures.
