# Playback Stream

FastAPI read API serving cached playback state over Redis/Firestore.
Clients poll `GET /state` (~2s with jitter); per-instance cache skew is
bounded by the cache TTLs (snapshot until song `endAt`, tallies ~500 ms,
listeners ~1 s).

## Endpoints
- `GET /state` -> current state snapshot (`currentSong`, `nextSong`, `poll`
  incl. `tallies` + `winnerOption`, `listeners`, `redisAvailable`, `ts`)
- `GET /health`

## Required env vars
- `REDIS_HOST`
- `REDIS_PORT`

## Optional env vars
- `STATIONS_COLLECTION` (default: `stations`)
- `VOTE_STATE_COLLECTION` (default: `voteState`)

## Run locally
```
docker compose -f services/playback-stream/docker-compose.yml up --build
```
