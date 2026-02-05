# Vote Orchestrator

FastAPI service triggered by Cloud Scheduler to create/rotate voting windows, close windows, compute winners from Redis, and publish window change events.

## Endpoints
- `POST /tick` -> create/rotate window
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `REDIS_URL`
- `VOTE_OPTIONS` (comma-separated) or `pulsefm-descriptors` (default)

## Optional env vars
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `WINDOW_SECONDS` (default: 300)
- `WINDOW_CHANGED_TOPIC` (default: `window-changed`)
- `OPTIONS_PER_WINDOW` (default: 4)
- `OPTIONS_PER_WINDOW` (default: 4)

## Run locally
```
docker compose -f services/vote-orchestrator/docker-compose.yml up --build
```

## Cloud Scheduler
Configure Cloud Scheduler to `POST /tick` on a cadence (e.g., every minute).

## Pub/Sub
Publishes window change events to the `window-changed` topic.

## Window options
- If `VOTE_OPTIONS` is set, the orchestrator uses that list every window.
- Otherwise it randomly samples 4 options from the keys in `pulsefm-descriptors`.
