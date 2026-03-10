# Playback Worker (Cloudflare, Python)

Python Cloudflare Worker + Durable Object service that owns station playback state.

## Project structure

- `wrangler.toml`: Cloudflare Worker and D1 bindings for this service.
- `src/entry.py`: Wrangler entry shim that re-exports Worker classes.
- `src/pulsefm_playback_worker/`: Python package for orchestration/runtime logic.
- `migrations/d1/`: D1 schema migrations.
- `tests/`: unit tests for orchestration behavior.

## Local development

```bash
cd apps/playback-worker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

Run the worker locally with Wrangler:

```bash
wrangler dev --config apps/playback-worker/wrangler.toml
```

## API

- `GET /state`: return the current station state snapshot.
- `POST /start`: initialize playback loop if it has not started yet.

## Runtime behavior

1. Start state sets `current_song`, selects `next_song` from D1 (`status='ready'`, fallback to stubbed song), and opens a poll with 4 options.
2. Alarm closes poll at `poll.end_at` by setting `is_open=false`.
3. Alarm advances loop at `current_song.end_at`: promote `next_song` to `current_song`, fetch a new `next_song`, and open a new poll.

The Durable Object always schedules its alarm for the next due event time.
