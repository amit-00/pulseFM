# 0003. Synchronous Authoritative Vote Tally

Date: 2026-07-15
Status: Accepted

## Context

Before WP-B (state at `0ae5bfb^`), a vote took an asynchronous detour: vote-api
validated the request with four sequential Redis reads (snapshot GET, status check,
`HKEYS` for options, `SISMEMBER` for dedupe), returned 200, and enqueued a Cloud
Task on `tally-queue` targeting `functions/tally-function`, which performed the
*authoritative* Lua dedupe + increment later and published to the `tally` topic. A
vote could pass validation, get a 200, and then silently fail to count (task
delivery failure, or losing the race to a duplicate). The 200 the client saw was a
promise, not a result.

## Decision

Make the vote path synchronous and authoritative (WP-B, merged in `6617b1f`):

- `SUBMIT_VOTE_LUA` (`packages/pulsefm-redis/pulsefm_redis/client.py`) performs
  validation, dedupe, and tally in a single Redis round-trip: check the playback
  snapshot exists and matches the submitted `voteId`, check `poll.status == "OPEN"`,
  check the option exists in the tally hash (`HEXISTS`), then `SADD` the session
  into the voted set and `HINCRBY` the tally only on first vote.
- vote-api (`services/vote-api/pulsefm_vote_api/main.py`) calls
  `submit_vote_atomic` in the request and maps results to an authoritative
  contract: `ok` → 200, `duplicate` → 409, `closed` → 409, `not_current` → 400,
  `invalid_option` → 400, `no_state` → 503, Redis unreachable → 503.
- No tally event is published — polling (ADR 0002) removed the only consumer.
- Deleted (`92a3c62`, `ae0cbb2`): `functions/tally-function`, the `tally-queue`
  Cloud Tasks queue, the `tally` Pub/Sub topic, the enqueue path in vote-api, and
  the related Terraform/IAM (including the orphaned Cloud Tasks enqueuer binding).
- The client surfaces the authoritative result (`2ba2cc4`): a 409 "Duplicate vote"
  keeps the user's selection; other failures roll back the optimistic UI and show
  the error.

## Consequences

- Clients get honest results: a 200 means the vote is counted in Redis, and
  duplicates/closed polls are visible as 409s instead of silent no-ops.
- A Redis outage now returns 503 ("Voting temporarily unavailable") instead of
  accepting votes that would never count. The client disables voting while
  `redisAvailable` is false.
- The queue's spike-buffering is lost. Accepted: the Lua call is O(1) and the real
  ceilings (vote-api instance count, shared VPC connector throughput) are far beyond
  hobby scale.
- Follow-up fix (`a5fdad1`): the voted-set TTL was never actually applied — Redis
  deletes empty sets immediately, so the `EXPIRE` in poll initialization landed on a
  nonexistent key and the first vote recreated the set with no TTL, leaking one key
  per poll. `POLL_OPEN_LUA` (and `init_poll_voted_set`) now `SADD` an `"__init__"`
  sentinel before the `EXPIRE` so the TTL sticks; the sentinel never matches a real
  session id.
