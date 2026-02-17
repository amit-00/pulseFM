# Playback Stream

FastAPI service that streams system state and tally updates over SSE.

## Endpoints
- `GET /state` -> current state snapshot
- `GET /stream` -> Server-Sent Events stream (requires `X-Session-Id`)
- `GET /health`

## Event types
- `HELLO`
- `TALLY_SNAPSHOT`
- `TALLY_DELTA`
- `SONG_CHANGED`
- `VOTE_CLOSED`
- `HEARTBEAT`

## Required env vars
- `REDIS_HOST`
- `REDIS_PORT`

## Optional env vars
- `STREAM_INTERVAL_MS` (default: 500)
- `TALLY_SNAPSHOT_INTERVAL_SEC` (default: 10)
- `HEARTBEAT_SEC` (default: 15)
- `STATIONS_COLLECTION` (default: `stations`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)

## Run locally
```
docker compose -f services/playback-stream/docker-compose.yml up --build
```
