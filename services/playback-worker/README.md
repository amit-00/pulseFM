# Playback Worker (Cloudflare, Python)

Python Cloudflare Worker + Durable Object service that owns station playback state.

## API

- `GET /state`: Return the current station state snapshot.
- `POST /start`: Initialize playback loop if it has not started yet.

## Station state

- `current_song`: `{ songId, duration_ms, start_at, end_at }`
- `next_song`: `{ songId, duration_ms }`
- `poll`: `{ options, start_at, end_at, is_open }`

## Playback loop

1. Start state sets `current_song`, selects `next_song` from D1 (`status='ready'`, fallback to stubbed song), and opens a poll with 4 options.
2. Alarm closes poll at `poll.end_at` by setting `is_open=false`.
3. Alarm advances loop at `current_song.end_at`: promote `next_song` to `current_song`, fetch a new `next_song`, and open a new poll.

The Durable Object always schedules its alarm for the next due event time.
