# Vote API

FastAPI service for accepting votes with a session id header.

## Endpoints
- `POST /vote` -> records the vote atomically in Redis and returns the authoritative result
- `GET /health`

## HTTP contract for `POST /vote`
- 200 `{"status": "ok"}` — counted
- 409 `detail="Duplicate vote"` — this session already voted
- 409 `detail="Vote closed"` — poll is no longer OPEN
- 400 `detail="Invalid voteId"` — not the current poll
- 400 `detail="Invalid option"` — unknown option
- 503 `detail="Vote state unavailable"` — no playback snapshot in Redis
- 503 `detail="Voting temporarily unavailable (Redis unreachable)"` — Redis error

## Required env vars
- `REDIS_HOST`
- `REDIS_PORT` (default: `6379`)

## Run locally
```
docker compose -f services/vote-api/docker-compose.yml up --build
```

## Session header
All session-required endpoints expect `X-Session-Id`.

## Dedupe
A single Lua script validates the current poll (voteId, OPEN status, option)
and performs the dedupe against the Redis `pulsefm:poll:{voteId}:voted` set
plus the tally increment in one atomic round-trip.
