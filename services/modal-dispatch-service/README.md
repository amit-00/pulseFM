# Modal Dispatch Service

FastAPI service that handles Modal generation orchestration from vote events.

## Endpoints
- `POST /events/vote`
- `POST /warmup`
- `GET /health`

## Behavior
- On vote `OPEN`, reads `endAt` and schedules `/warmup` for `endAt - 30s`.
- Warmup is skipped when there are no active listeners.
- On vote `CLOSE`, enforces idempotency by `voteId`, scales Modal min instances to `1`, awaits generation completion, then retries scaling to `0` for up to 5 minutes.

## Required env vars
- `PROJECT_ID`
- `LOCATION`
- `MODAL_DISPATCH_SERVICE_URL`
- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`
- `REDIS_HOST`
- `REDIS_PORT`

## Optional env vars
- `MODAL_QUEUE_NAME` (default: `playback-queue`)
- `WARMUP_LEAD_SECONDS` (default: `30`)
- `SCALE_DOWN_RETRY_HORIZON_SECONDS` (default: `300`)
- `SCALE_DOWN_RETRY_DELAY_SECONDS` (default: `5`)
- `HEARTBEAT_ACTIVE_KEY` (default: `pulsefm:heartbeat:active`)
- `CLOSE_DONE_TTL_SECONDS` (default: `86400`)
- `CLOSE_LOCK_TTL_SECONDS` (default: `600`)
- `MODAL_APP_NAME` (default: `pulsefm-worker`)
- `MODAL_CLASS_NAME` (default: `MusicGenerator`)
- `MODAL_METHOD_NAME` (default: `generate`)
- `MODAL_FUNCTION_NAME` (default: `MusicGenerator.generate`)

## Run locally
```
docker compose -f services/modal-dispatch-service/docker-compose.yml up --build
```
