# Vote API

FastAPI service for accepting votes and downloads with a session id header.

## Endpoints
- `POST /vote` -> submits a vote (pre-checks dedupe via Redis, then enqueues)
- `POST /downloads` -> signed URL for encoded audio
- `POST /heartbeat` -> heartbeat (rate limited)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `TALLY_FUNCTION_URL`

## Optional env vars
- `VOTE_QUEUE_NAME` (default: `tally-queue`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (optional service account email for Cloud Tasks OIDC)

## Run locally
```
docker compose -f services/vote-api/docker-compose.yml up --build
```

## Session header
All session-required endpoints expect `X-Session-Id`.

## Cloud Tasks
Votes are enqueued to the `tally-queue` Cloud Tasks queue with JSON payloads:
```
{
  "voteId": "...",
  "option": "...",
  "sessionId": "...",
  "votedAt": "2024-01-01T00:00:00Z",
  "version": 1
}
```

## Dedupe
Votes are pre-checked against the Redis `pulsefm:poll:{voteId}:voted` set before enqueueing.
