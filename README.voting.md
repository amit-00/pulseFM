# Voting System (Vote API + Tally Worker + Orchestrator + Playback Orchestrator)

This repo includes four FastAPI services and one Cloud Function that implement an anonymous voting system on Cloud Run:

- **vote-api**: issues anonymous session cookies, accepts votes, dedupes, enqueues Cloud Tasks
- **tally-function**: receives Cloud Tasks, updates Redis tallies idempotently
- **playback-service**: advances station playback, closes/open votes, and publishes vote events
- **vote-stream**: streams current poll state/tallies over SSE from Redis
- **modal-dispatcher** (Cloud Function): dispatches the Modal worker on vote close when listeners are active

## Firestore schema

### `voteState` (doc: `current`)
Pointer document read by all services:

```json
{
  "voteId": "string",
  "status": "OPEN | CLOSED",
  "startAt": "timestamp",
  "endAt": "timestamp",
  "options": ["string"],
  "version": "number",
  "createdAt": "timestamp",
  "closedAt": "timestamp (optional)"
}
```

### `voteWindows` (doc: `{voteId}`)
History document per window:

```json
{
  "voteId": "string",
  "status": "OPEN | CLOSED",
  "startAt": "timestamp",
  "endAt": "timestamp",
  "options": ["string"],
  "winnerOption": "string (set on close)",
  "version": "number",
  "createdAt": "timestamp",
  "closedAt": "timestamp"
}
```

### Redis keys (canonical tally + dedupe)

- `pulsefm:poll:current` -> current `voteId`
- `pulsefm:poll:{voteId}:state` -> HASH: `status`, `opensAt` (epoch ms), `closesAt` (epoch ms)
- `pulsefm:poll:{voteId}:tally` -> HASH: `option` => count
- `pulsefm:poll:{voteId}:voted` -> SET of sessionIds

### `stations` (doc: `main`)

```json
{
  "voteId": "string",
  "startAt": "timestamp",
  "endAt": "timestamp",
  "durationMs": "number",
  "next": {
    "voteId": "string",
    "duration": "number"
  },
  "version": "number"
}
```

### `songs` (doc: `{voteId}`)

```json
{
  "durationMs": "number",
  "createdAt": "timestamp",
  "status": "ready | played"
}
```

### `songs` (doc: `stubbed`)

```json
{
  "voteId": "string",
  "durationMs": "number"
}
```

## Cloud Tasks

Queues:
- `tally-queue` (vote-api -> tally-function)
- `playback-queue` (playback-service -> playback-service)

## Service responsibilities

### vote-api
- `POST /session` issues a signed JWT session cookie (HMAC)
- `POST /vote` validates session, rate-limits, pre-checks dedupe, and enqueues a Cloud Task

### tally-function
- HTTP function that handles Cloud Tasks and performs the atomic Redis vote operation idempotently

### playback-service
- `POST /tick` advances station playback, closes/open votes, publishes vote events, and schedules the next playback tick

### vote-stream
- `GET /stream` streams SSE updates (full snapshot on connect/open/close, diffs between)

### modal-dispatcher
- Pub/Sub triggered (CLOSE events) to dispatch the Modal worker when listeners are active

## Pub/Sub

Topics:
- `vote-events` (published by playback-service)
- `playback` (published by playback-service)

Consumers:
- `modal-dispatcher` (CLOSE events from `vote-events`)

Message payload:
```json
{
  "event": "OPEN | CLOSE",
  "voteId": "string",
  "winnerOption": "string (CLOSE only)"
}
```

Playback payload:
```json
{
  "event": "CHANGEOVER",
  "durationMs": "number"
}
```

## Required environment variables

### vote-api
- `PROJECT_ID`
- `LOCATION`
- `SESSION_JWT_SECRET`
- `TALLY_FUNCTION_URL`

### tally-function
- no Firestore envs required (Redis only)

### playback-service
- `PROJECT_ID`
- `LOCATION`

### vote-stream
- `SESSION_JWT_SECRET`

## Cloud Run deployment notes

- Build from repo root so workspace packages are available.
- For each service, use its `services/<name>/Dockerfile`.
- Ensure ADC or service account credentials are configured for Firestore + Cloud Tasks.
