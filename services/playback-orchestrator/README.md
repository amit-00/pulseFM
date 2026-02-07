# Playback Orchestrator

FastAPI service that updates the live station state from the next ready song and enqueues a vote-orchestrator open request.

## Endpoint
- `POST /tick`
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `VOTE_ORCHESTRATOR_URL` (include `/open`)

## Optional env vars
- `STATIONS_COLLECTION` (default: `stations`)
- `SONGS_COLLECTION` (default: `songs`)
- `VOTE_ORCHESTRATOR_QUEUE` (default: `vote-orchestrator-queue`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (service account email for Cloud Tasks OIDC)

## Song selection
- Selects the oldest `songs` document with `status == "ready"` ordered by `createdAt`.
- If none exists, reads `songs/stubbed` with schema `{ voteId, duration }` and uses that.

## Station update
In a single transaction, it updates `stations/main` and marks the selected song `played` (if not stubbed).

## Run locally
```
docker compose -f services/playback-orchestrator/docker-compose.yml up --build
```
