# Vote Orchestrator

FastAPI service to open/close votes and compute winners from Firestore tallies.

## Endpoints
- `POST /open` -> open a new vote (requires JSON body with `endsAt`)
- `POST /close` -> close the current vote (idempotent)
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `VOTE_OPTIONS` (comma-separated) or `pulsefm-descriptors` (default)

## Optional env vars
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `WINDOW_SECONDS` (default: 300)
- `OPTIONS_PER_WINDOW` (default: 4)

## Run locally
```
docker compose -f services/vote-orchestrator/docker-compose.yml up --build
```

## Trigger
Use Cloud Tasks (from playback-orchestrator) to call `POST /open` with `{ "endsAt": "<iso8601>" }`.

## Window options
- If `VOTE_OPTIONS` is set, the orchestrator uses that list every window.
- Otherwise it randomly samples 4 options from the keys in `pulsefm-descriptors`.
