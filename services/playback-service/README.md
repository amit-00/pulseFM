# Playback Service

FastAPI service that performs song changeover and rotates votes in one flow.

## Endpoint
- `POST /tick`
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `PLAYBACK_TICK_URL` (base service URL)

## Optional env vars
- `STATIONS_COLLECTION` (default: `stations`)
- `SONGS_COLLECTION` (default: `songs`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_WINDOWS_COLLECTION` (default: `voteWindows`)
- `VOTE_EVENTS_TOPIC` (default: `vote-events`)
- `PLAYBACK_EVENTS_TOPIC` (default: `playback`)
- `WINDOW_SECONDS` (default: 300)
- `OPTIONS_PER_WINDOW` (default: 4)
- `VOTE_OPTIONS` (comma-separated)
- `PLAYBACK_QUEUE_NAME` (default: `playback-queue`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (service account email for Cloud Tasks OIDC)

## Behavior
- Updates station playback and marks songs played.
- Closes any open vote and opens a new one.
- Publishes vote OPEN/CLOSE events and playback CHANGEOVER.
- Schedules the next tick based on the current song duration.

## Run locally
```
docker compose -f services/playback-service/docker-compose.yml up --build
```
