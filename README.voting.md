# Voting System (Vote API + Tally Worker + Orchestrator + Playback Orchestrator)

This repo includes four FastAPI services that implement an anonymous voting system on Cloud Run:

- **vote-api**: issues anonymous session cookies, accepts votes, dedupes, enqueues Cloud Tasks
- **tally-function**: receives Cloud Tasks, updates Redis tallies idempotently
- **vote-orchestrator**: rotates vote windows in Firestore and dispatches the music worker
- **playback-orchestrator**: advances station playback and triggers vote-orchestrator ticks

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
- `vote-orchestrator-queue` (playback-orchestrator -> vote-orchestrator)
- `playback-queue` (playback-orchestrator -> playback-orchestrator)

## Service responsibilities

### vote-api
- `POST /session` issues a signed JWT session cookie (HMAC)
- `POST /vote` validates session, rate-limits, pre-checks dedupe, and enqueues a Cloud Task

### tally-function
- HTTP function that handles Cloud Tasks and performs the atomic Redis vote operation idempotently

### vote-orchestrator
- `POST /open` creates/rotates votes (requires `endsAt` in payload)
- `POST /close` closes the current vote idempotently (requires `voteId` in payload)
- On close, persists `voteWindows` and dispatches the Modal worker if listeners exist

### playback-orchestrator
- `POST /tick` advances station playback, marks songs played, enqueues a vote-orchestrator open request, and schedules the next playback tick

## Required environment variables

### vote-api
- `PROJECT_ID`
- `LOCATION`
- `SESSION_JWT_SECRET`
- `TALLY_FUNCTION_URL`

### tally-function
- no Firestore envs required (Redis only)

### vote-orchestrator
- `PROJECT_ID`

### playback-orchestrator
- `PROJECT_ID`
- `LOCATION`
- `VOTE_ORCHESTRATOR_URL`

## Cloud Run deployment notes

- Build from repo root so workspace packages are available.
- For each service, use its `services/<name>/Dockerfile`.
- Ensure ADC or service account credentials are configured for Firestore + Cloud Tasks.
