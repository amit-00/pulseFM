# Playback Worker (Cloudflare, Python)

Python Cloudflare Worker + Durable Object replacement for `services/playback-service`.

## Public endpoint

- `GET /state`

## Storage model

- Durable Object (`PlaybackStateDurableObject`) is canonical for playback state + scheduling.
- D1 (`PLAYBACK_DB`) stores song rows used for candidate selection (`ready -> queued -> played`).

## Scheduling model

Playback orchestration is internal and alarm-driven only.  
The DO keeps a persisted scheduled-event queue and runs all changeover/poll-close logic from alarm handlers.

## Trust model (migration phase)

Temporary network-level trust: no app-layer auth in this service yet.
