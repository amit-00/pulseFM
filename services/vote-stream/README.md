# Vote Stream

FastAPI service that streams current poll state and tallies over SSE.

## Endpoint
- `GET /stream` -> Server-Sent Events stream (requires session cookie)
- `GET /health`

## Event types
- `poll` -> full snapshot on connect, reconnects, and poll open/close
- `tally` -> diffs between polls with changed option counts

## Required env vars
- `SESSION_JWT_SECRET`
- `REDIS_HOST`
- `REDIS_PORT`

## Optional env vars
- `SESSION_COOKIE_NAME` (default: `pulsefm_session`)
- `STREAM_INTERVAL_MS` (default: 500)

## Run locally
```
docker compose -f services/vote-stream/docker-compose.yml up --build
```
