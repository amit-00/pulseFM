# Playback Service

FastAPI service that performs song changeover and rotates votes in one flow.

## Endpoint
- `POST /tick`
- `POST /vote/close`
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
- `POST /vote/close` only closes the current vote when both `voteId` and `version` match `voteState/current`.
- `POST /tick` closes current vote only when it is open, then opens a new vote.
- Maintains poll lifecycle state in Redis `pulsefm:playback:current` via `poll.status` (`OPEN`/`CLOSED`).
- Publishes vote OPEN/CLOSE events and playback CHANGEOVER.
- Schedules the next tick based on the current song duration.
- Schedules a delayed vote-close task 40 seconds before the next tick (or immediately for songs shorter than 40 seconds).

## Run locally
```
docker compose -f services/playback-service/docker-compose.yml up --build
```
