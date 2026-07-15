# 0004. Fire-and-Forget Modal Dispatch via .spawn() + Delayed Scale-Down

Date: 2026-07-15
Status: Accepted

## Context

Before WP-C (state at `7e05b17^`), the vote-CLOSE handler in
`services/modal-dispatch-service` ran the whole GPU generation synchronously inside
an Eventarc push webhook: scale Modal to `min_containers=1`, block on
`method.remote(...)` until the song was generated, then scale back to 0 — all in
one request. A mid-flight kill (Eventarc/Cloud Run timeout, instance SIGTERM) could
strand `min_containers=1` (paying for a warm GPU indefinitely), skip the close-done
marker, and leave the close lock to expire on TTL.

## Decision

Make dispatch fire-and-forget (WP-C, merged in `3cfa30b`), in
`services/modal-dispatch-service/pulsefm_modal_dispatch_service/main.py`:

- The CLOSE handler calls `method.spawn(...)` and returns as soon as the Modal
  function call is accepted. The function-call id is stored in Redis
  (`pulsefm:modal:call:{voteId}`, TTL = `max(60, 2 × GENERATION_HORIZON_SECONDS)`),
  close-done is marked immediately after a successful spawn, and the lock is
  released.
- At spawn time the handler enqueues a **delayed Cloud Task** on
  `modal-dispatch-queue` (task id `modal-scaledown-{voteId}`, delay =
  `GENERATION_HORIZON_SECONDS`, 600 s default, `ignore_already_exists=True`)
  targeting a new idempotent `POST /scaledown` endpoint.
- `/scaledown` sets `min_containers=0` using the existing retry helper
  (`_set_min_instances_zero_with_retry`), then polls the stored function-call id:
  it logs **ERROR** if the generation failed (restoring the failure signal the
  blocking `.remote()` used to provide) and WARNING if it is still running at the
  horizon.
- `update_autoscaler(min_containers=0)` does not kill in-flight calls, so an
  overlapping next-vote generation is safe (worst case: a lost warm start).
- Alongside WP-C, all Cloud Run services got explicit timeouts in
  `terraform/cloud_run.tf` (vote-api 30 s, encoder 300 s, playback-service 120 s,
  modal-dispatch-service 60 s; playback-stream 60 s via WP-A): no handler blocks
  long enough to need the 300 s default anymore.

## Consequences

- The webhook completes in milliseconds; a SIGTERM elsewhere can no longer strand
  warm GPU spend, because scale-down is owned by a durable, idempotent, per-voteId
  Cloud Task rather than the tail of a long-lived request.
- The failure signal moved from HTTP request errors to ERROR logs on `/scaledown`
  ("Modal generation failed; station will fall back to stubbed song"). Nothing
  retries a failed generation — rotation's stubbed-song fallback covers the gap,
  which is the accepted behavior.
- Scale-down now depends on Cloud Tasks delivery. The task is named per voteId and
  idempotent, so retries are safe; the next vote cycle's warmup/scaledown pair also
  bounds how long a missed task could leave `min_containers=1`.
- If Redis is down when the call id is stored or read, `/scaledown` still scales to
  zero but reports the generation status as "unknown" (WARNING-level degradation).
