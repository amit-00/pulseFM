# 0002. Client Polling of /state Replaces SSE Streaming

Date: 2026-07-15
Status: Accepted

## Context

Before the hardening work (state at `8b41395^`), `services/playback-stream` pushed
updates over Server-Sent Events:

- `GET /stream` held every listener's connection open and drove it with a
  `while True: ... await asyncio.sleep(0.05)` loop — a 50 ms busy-poll per
  connected client, each occupying a Cloud Run concurrency slot for the lifetime of
  the connection, with no explicit request timeout configured.
- Event markers (`last_invalidated`, `last_vote_closed`, `last_next_song_changed`,
  `last_playback_version`) lived in per-instance `StreamState` memory, fed by three
  Eventarc ingest endpoints (`POST /events/tally`, `/events/playback`,
  `/events/vote`). Replicas could disagree about dirty tallies and vote closes, and
  the vote winner traveled only inside the in-memory SSE event stream.

## Decision

Replace SSE with client polling of `GET /state` (WP-A, merged in `8c96b72`):

- **Server** (`services/playback-stream/pulsefm_playback_stream/main.py`): the SSE
  endpoint, event-loop machinery, and Eventarc ingest endpoints are deleted.
  `StreamState` is reduced to short-TTL read-through caches over shared stores:
  the playback snapshot (TTL = current song `endAt`), tallies
  (`TALLY_CACHE_STALENESS_MS = 500`), and listener count
  (`LISTENER_CACHE_STALENESS_MS = 1000`). `/state` keeps its response shape
  (snapshot + `poll.tallies` + `winnerOption` + `listeners` + `redisAvailable`).
- **Winner propagation**: `playback-service` now writes `winnerOption` into the
  Redis playback snapshot when closing a vote
  (`set_playback_poll_status(..., winner_option=...)` in
  `packages/pulsefm-redis/pulsefm_redis/client.py`), with the Firestore
  `voteState/current` document as fallback.
- **Client** (`client/lib/pollDiff.ts`, `client/hooks/useStreamPlayer.ts`): polls
  `/api/playback/state` every 2 s plus 0–500 ms jitter, wakes ~300 ms after the
  known song `endAt` boundary so changeovers feel instant, and refetches
  immediately after submitting a vote. UI transitions are derived by diffing
  consecutive snapshots (`currentSong.voteId` change ⇒ song changed; `poll.status`
  OPEN→CLOSED ⇒ vote closed; `nextSong` change ⇒ prefetch). The
  `/api/playback/stream` proxy route is deleted.
- **Dead infrastructure removed** (`721bf09`, `f6265d8`): the `playback` Pub/Sub
  topic and its `NEXT-SONG-CHANGED`/`CHANGEOVER` publishes in playback-service, and
  the Eventarc triggers targeting playback-stream. The `vote-events` topic is
  retained — modal-dispatch-service still consumes OPEN/CLOSE. playback-stream gets
  an explicit 60 s Cloud Run timeout (polls are millisecond requests; the timeout is
  hygiene, not a streaming contract).

## Consequences

- Tally freshness drops to roughly the poll interval: up to ~2.5 s in the worst case
  (2 s + jitter poll, plus ≤500 ms server-side tally cache). Accepted for a hobby
  radio UI.
- Per-instance divergence is now bounded by cache TTLs (~0.5–2 s skew between
  replicas) instead of unbounded event-marker drift; this bound is a deliberate,
  documented tradeoff.
- No long-lived connections: 1,000 concurrent listeners ≈ 500 req/s of cache-served
  reads, and Redis is touched a few times per second per instance regardless of
  listener count.
- Losing push means no sub-second "vote closed" flash; the boundary-scheduled poll
  keeps song changeover timing tight.
