# Cloudflare Backend Migration

Playback service migration is now implemented as a **Python** Cloudflare Worker + Durable Object + D1.

## Implemented slice

- Worker + Durable Object entrypoint: `services/playback-worker/src/entry.py`
- D1 schema: `services/playback-worker/migrations/d1/0001_init.sql`
- Wrangler deployment config: `infra/cloudflare/wrangler.toml`

## Runtime model

- `PlaybackStateDurableObject` is canonical for playback state and scheduling.
- Worker exposes `GET /state` and `POST /start`.
- Playback orchestration loop is alarm-driven after initialization.
- D1 stores song rows used for candidate selection and state transitions.
- Event-bus compatibility with previous GCP Pub/Sub/Eventarc flow is intentionally dropped.
- Temporary network-level trust model is in effect (no app-level auth yet).

## Local checks

```bash
./scripts/cloudflare/validate.sh
```

## Deploy flow (GitHub Actions)

Workflow: `.github/workflows/cloudflare-deploy.yml`

Required repo secrets:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Required repo variable to enable deployment:
- `ENABLE_CLOUDFLARE_BACKEND_DEPLOY=true`
