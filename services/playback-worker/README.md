# Playback Worker (Cloudflare, Python)

Python Cloudflare Worker + Durable Object replacement for `services/playback-service`.

## Endpoints

- `POST /tick`
- `POST /vote/close`
- `POST /next/refresh`
- `POST /songs/upsert` (temporary migration helper)
- `GET /state`
- `GET /health`

## Storage model

- Durable Object (`PlaybackStateDurableObject`) is canonical for playback state + scheduling.
- D1 (`PLAYBACK_DB`) stores song rows used for candidate selection (`ready -> queued -> played`).

## Scheduling model

The DO uses a persisted scheduled-event queue and a single DO alarm:
- `tick:<version>` for next rotation
- `close:<voteId>:<version>` for vote close

## Trust model (migration phase)

Temporary network-level trust: no app-layer auth in this service yet.
