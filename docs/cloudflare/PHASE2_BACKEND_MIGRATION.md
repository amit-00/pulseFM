# Phase 2 Backend Migration Backlog

## Completed

1. Migrated playback orchestration to Cloudflare Worker + Durable Object + D1.

## Remaining migration sequence

1. Migrate `vote-api` request handling and tally flow.
2. Migrate `playback-stream` SSE state fanout.
3. Migrate `encoder` event-trigger pipeline.
4. Migrate `modal-dispatch-service` warmup/dispatch path.
5. Rewire web/API proxy targets from GCP endpoints to Cloudflare endpoints.

## Cutover checkpoints

1. Confirm service-level parity tests pass in staging replay.
2. Validate Cloudflare managed secret parity with runtime requirements.
3. Validate failure handling (alarm retries, stale version requests, D1 contention).
4. Run canary cutover per service with rollback procedures.
5. Confirm observability parity (error rate, latency, queue depth, stream stability).
6. Execute production cutover and lock verification checklist.
