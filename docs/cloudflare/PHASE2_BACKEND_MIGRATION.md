# Phase 2 Backend Migration Backlog

## Proposed migration sequence

1. Migrate `vote-api` request handling and queue-dispatch flow.
2. Migrate `playback-service` orchestration endpoints and scheduling contracts.
3. Migrate `playback-stream` state + SSE fanout behavior.
4. Migrate `encoder` event-trigger pipeline.
5. Migrate `modal-dispatch-service` warmup/dispatch path.
6. Rewire client/API proxy targets from GCP endpoints to Cloudflare endpoints.

## Cutover checkpoints

1. Confirm per-service parity tests pass in staging traffic replay.
2. Validate secret parity (Cloudflare managed secrets vs existing runtime values).
3. Validate queue/event behavior under retry and out-of-order delivery.
4. Run canary cutover per service with rollback procedure documented.
5. Confirm observability parity (error rate, latency, queue depth, stream stability).
6. Execute production cutover window and lock post-cutover verification checklist.
