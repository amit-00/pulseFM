# Playback Service

FastAPI service that performs song changeover and rotates votes in one flow.

## Endpoint
- `POST /tick` (payload requires `version`)
- `POST /vote/close`
- `POST /next/replace-if-stubbed`
- `GET /health`

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `PLAYBACK_TICK_URL` (base service URL)

## Optional env vars
- `STATIONS_COLLECTION` (default: `stations`)
- `SONGS_COLLECTION` (default: `songs`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)
- `VOTE_EVENTS_TOPIC` (default: `vote-events`)
- `PLAYBACK_EVENTS_TOPIC` (default: `playback`)
- `WINDOW_SECONDS` (default: 300)
- `OPTIONS_PER_WINDOW` (default: 4)
- `VOTE_OPTIONS` (comma-separated)
- `PLAYBACK_QUEUE_NAME` (default: `playback-queue`)
- `TASKS_OIDC_SERVICE_ACCOUNT` (service account email for Cloud Tasks OIDC)

## Behavior
- Updates station playback and marks songs played.
- `POST /next/replace-if-stubbed` replaces `stations/main.next` only when next is `stubbed`, marks the selected song `queued`, and reconciles redis snapshot `nextSong` for both `updated` and `already_set` responses.
- `POST /next/replace-if-stubbed` emits `NEXT-SONG-CHANGED` only when reconciliation detects redis `nextSong` was out of sync.
- `POST /vote/close` only closes the current vote when both `voteId` and `version` match `voteState/current`.
- `POST /tick` closes current vote only when it is open, then opens a new vote. It promotes `stations/main.next` to current playback, marks the promoted song `played` (non-stubbed), and chooses the most recently `ready` song as the next candidate (fallback `stubbed`).
- `POST /tick` is version-gated for idempotency: if payload `version` is less than or equal to `stations/main.version`, it returns a noop response (`status: "noop"`) and performs no mutations.
- Maintains poll lifecycle state in Redis `pulsefm:playback:current` via `poll.status` (`OPEN`/`CLOSED`).
- Publishes vote OPEN/CLOSE events and playback `CHANGEOVER` plus `NEXT-SONG-CHANGED`.
- Schedules the next tick based on the current song duration.
- Schedules a delayed vote-close task 60 seconds before the next tick (or immediately for songs shorter than 60 seconds).
- Sets vote `endAt` to the close-task trigger time (separate from song `endAt`).

## Run locally
```
docker compose -f services/playback-service/docker-compose.yml up --build
```
