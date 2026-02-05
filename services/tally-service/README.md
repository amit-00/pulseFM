# Tally Service

FastAPI service that consumes Pub/Sub vote events, increments Redis tallies, and streams updates via SSE.

## Endpoints
- `GET /stream` -> Server-Sent Events stream
- `POST /pubsub/vote-events` -> Pub/Sub push handler
- `POST /pubsub/window-changed` -> Pub/Sub push handler (optional)
- `GET /health`

## Required env vars
- `REDIS_URL`

## Run locally
```
docker compose -f services/tally-service/docker-compose.yml up --build
```

## Pub/Sub push subscriptions
Configure push subscriptions for:
- Topic `vote-events` -> `POST /pubsub/vote-events`
- Topic `window-changed` -> `POST /pubsub/window-changed`

Payloads are decoded from Pub/Sub base64 data JSON.
