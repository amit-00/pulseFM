# Voting System (Vote API + Tally Service + Orchestrator)

This repo includes three FastAPI services that implement an anonymous voting system on Cloud Run:

- **vote-api**: issues anonymous session cookies, accepts votes, enforces rate limits + dedupe, publishes vote events
- **tally-service**: consumes vote events, increments Redis tallies, streams updates over SSE
- **vote-orchestrator**: rotates vote windows in Firestore, closes windows, computes winners from Redis, publishes window changes

## Firestore schema

### `voteState` (doc: `current`)
Pointer document read by all services:

```json
{
  "windowId": "string",
  "status": "OPEN | CLOSED",
  "startAt": "timestamp",
  "endAt": "timestamp",
  "options": ["string"],
  "version": "number",
  "createdAt": "timestamp",
  "closedAt": "timestamp (optional)"
}
```

### `voteWindows` (doc: `{windowId}`)
History document per window:

```json
{
  "windowId": "string",
  "status": "OPEN | CLOSED",
  "startAt": "timestamp",
  "endAt": "timestamp",
  "options": ["string"],
  "winnerOption": "string (set on close)",
  "tallies": { "optionString": "number" },
  "version": "number",
  "createdAt": "timestamp",
  "closedAt": "timestamp"
}
```

## Redis keys

- **Dedupe**: `vote:{windowId}:{sessionId}` → value = `option`
  - Set via `SET NX EX <ttl_seconds_remaining>`
- **Rate limits**:
  - `rl:s:{sessionId}:{yyyymmddhhmm}` → integer (INCR, EX 60)
  - `rl:ip:{ip}:{yyyymmddhhmm}` → integer (INCR, EX 60)
- **Tallies**: `tally:{windowId}:{option}` → integer (INCR)

## Pub/Sub topics

- Vote events: `vote-events`
- Window changes: `window-changed`

## Service responsibilities

### vote-api
- `POST /session` issues a signed JWT session cookie (HMAC)
- `GET /window` returns current window (from `voteState/current`)
- `POST /vote` validates session, rate-limits, dedupes, and publishes to Pub/Sub

### tally-service
- `POST /pubsub/vote-events` handles vote events and increments Redis tallies
- `POST /pubsub/window-changed` broadcasts window changes (optional)
- `GET /stream` SSE stream for real-time updates

### vote-orchestrator
- `POST /tick` (Cloud Scheduler) rotates windows and computes winners
  - Opens first window if none exists
  - Closes current window when expired, writes `voteWindows` history
  - Publishes `window-changed` events
- Window options are sampled randomly from `pulsefm-descriptors` (4 per window) unless `VOTE_OPTIONS` is set

## Required environment variables

### vote-api
- `PROJECT_ID`
- `SESSION_JWT_SECRET`
- `REDIS_URL`

### tally-service
- `REDIS_URL`

### vote-orchestrator
- `PROJECT_ID`
- `REDIS_URL`
- `VOTE_OPTIONS` (comma-separated) or `pulsefm-descriptors`

## Local development

```bash
# vote-api
bash services/vote-api/entrypoint.sh
# or
Docker compose -f services/vote-api/docker-compose.yml up --build

# tally-service
Docker compose -f services/tally-service/docker-compose.yml up --build

# vote-orchestrator
Docker compose -f services/vote-orchestrator/docker-compose.yml up --build
```

## Pub/Sub push subscriptions (example)

Configure push subscriptions to your Cloud Run service URLs:

- `vote-events` topic -> `POST https://<tally-service-url>/pubsub/vote-events`
- `window-changed` topic -> `POST https://<tally-service-url>/pubsub/window-changed`

## Cloud Scheduler

Set Scheduler to `POST https://<vote-orchestrator-url>/tick` every minute (or as needed).

## Cloud Run deployment notes

- Build from repo root so workspace packages are available.
- For each service, use its `services/<name>/Dockerfile`.
- Ensure ADC or service account credentials are configured for Firestore + Pub/Sub.
