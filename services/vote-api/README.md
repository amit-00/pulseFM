# Vote API

FastAPI service for issuing anonymous session cookies and accepting votes.

## Endpoints
- `POST /session` -> issues signed JWT cookie
- `POST /vote` -> submits a vote (pre-checks dedupe via Redis, then enqueues)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `SESSION_JWT_SECRET`
- `TALLY_FUNCTION_URL`

## Optional env vars
- `SESSION_COOKIE_NAME` (default: `pulsefm_session`)
- `SESSION_TTL_SECONDS` (default: 604800)
- `VOTE_QUEUE_NAME` (default: `tally-queue`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (optional service account email for Cloud Tasks OIDC)

## Run locally
```
docker compose -f services/vote-api/docker-compose.yml up --build
```

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
