# Vote Orchestrator

FastAPI service to open/close votes, compute winners from Redis tallies, and publish vote events.

## Endpoints
- `POST /open` -> open a new vote (requires JSON body with `endsAt`)
- `POST /close` -> close the current vote (idempotent, requires `voteId` in body)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `VOTE_OPTIONS` (comma-separated) or `pulsefm-descriptors` (default)
- `VOTE_ORCHESTRATOR_URL` (base service URL)
- `VOTE_EVENTS_TOPIC` (default: `vote-events`)

## Optional env vars
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `VOTE_ORCHESTRATOR_QUEUE` (default: `vote-orchestrator-queue`)
- `WINDOW_SECONDS` (default: 300)
- `OPTIONS_PER_WINDOW` (default: 4)
- `TASKS_OIDC_SERVICE_ACCOUNT` (service account email for Cloud Tasks OIDC)

## Run locally
```
docker compose -f services/vote-orchestrator/docker-compose.yml up --build
```

## Trigger
Use Cloud Tasks (from playback-orchestrator) to call `POST /open` with `{ "endsAt": "<iso8601>" }`.

## Window options
- If `VOTE_OPTIONS` is set, the orchestrator uses that list every window.
- Otherwise it randomly samples 4 options from the keys in `pulsefm-descriptors`.
