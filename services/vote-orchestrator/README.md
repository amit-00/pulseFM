# Vote Orchestrator

FastAPI service triggered by Cloud Scheduler to create/rotate voting windows, close windows, and compute winners from Firestore tallies.

## Endpoints
- `POST /tick` -> create/rotate window
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `VOTE_OPTIONS` (comma-separated) or `pulsefm-descriptors` (default)

## Optional env vars
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `WINDOW_SECONDS` (default: 300)
- `OPTIONS_PER_WINDOW` (default: 4)
- `OPTIONS_PER_WINDOW` (default: 4)

## Run locally
```
docker compose -f services/vote-orchestrator/docker-compose.yml up --build
```

## Cloud Scheduler
Configure Cloud Scheduler to `POST /tick` on a cadence (e.g., every minute).

## Window options
- If `VOTE_OPTIONS` is set, the orchestrator uses that list every window.
- Otherwise it randomly samples 4 options from the keys in `pulsefm-descriptors`.
