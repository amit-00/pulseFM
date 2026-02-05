# Vote API

FastAPI service for issuing anonymous session cookies and accepting votes.

## Endpoints
- `POST /session` -> issues signed JWT cookie
- `GET /window` -> returns current voting window
- `POST /vote` -> submits a vote (deduped via Firestore)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `SESSION_JWT_SECRET`
- `TALLY_WORKER_URL`

## Optional env vars
- `SESSION_COOKIE_NAME` (default: `pulsefm_session`)
- `SESSION_TTL_SECONDS` (default: 604800)
- `VOTE_QUEUE_NAME` (default: `vote-queue`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `VOTES_COLLECTION` (default: `votes`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (optional service account email for Cloud Tasks OIDC)

## Run locally
```
docker compose -f services/vote-api/docker-compose.yml up --build
```

## Cloud Tasks
Votes are enqueued to the `vote-queue` Cloud Tasks queue with JSON payloads:
```
{
  "windowId": "...",
  "option": "...",
  "sessionId": "...",
  "votedAt": "2024-01-01T00:00:00Z",
  "version": 1
}
```

## Dedupe
Votes are deduped via the `votes` Firestore collection keyed by `{windowId}:{sessionId}`.
