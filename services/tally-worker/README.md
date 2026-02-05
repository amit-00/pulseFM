# Tally Worker

FastAPI service that receives Cloud Tasks and updates Firestore vote tallies idempotently.

## Endpoint
- `POST /task/vote` -> increments tallies for the current window
- `GET /health`

## Required env vars
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTES_COLLECTION` (default: `votes`)

## Run locally
```
docker compose -f services/tally-worker/docker-compose.yml up --build
```

## Idempotency
Votes are deduped by document ID: `{windowId}:{sessionId}` in the `votes` collection. The worker sets `counted=true` once tallies are incremented.
