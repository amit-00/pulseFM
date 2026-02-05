# Vote API

FastAPI service for issuing anonymous session cookies and accepting votes.

## Endpoints
- `POST /session` -> issues signed JWT cookie
- `GET /window` -> returns current voting window
- `POST /vote` -> submits a vote (rate limited + deduped)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `SESSION_JWT_SECRET`
- `REDIS_URL`

## Optional env vars
- `SESSION_COOKIE_NAME` (default: `pulsefm_session`)
- `SESSION_TTL_SECONDS` (default: 604800)
- `VOTE_EVENTS_TOPIC` (default: `vote-events`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `RL_SESSION_PER_MIN` (default: 10)
- `RL_IP_PER_MIN` (default: 60)

## Run locally
```
docker compose -f services/vote-api/docker-compose.yml up --build
```

## Pub/Sub push subscription
Vote events are published to the `vote-events` topic as JSON payloads:
```
{
  "windowId": "...",
  "option": "...",
  "sessionId": "...",
  "votedAt": "2024-01-01T00:00:00Z",
  "version": 1
}
```
