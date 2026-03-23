# PulseFM

PulseFM is an AI-generated radio station with live voting and continuous playback. This branch migrates the application to a Cloudflare-native runtime:

- **Cloudflare Pages** serves the frontend as a static Next.js export.
- **Cloudflare Worker** handles the public API.
- **Durable Objects** own playback rotation, active poll state, vote tallying, and presence.
- **D1** stores the light song/poll/job catalog.
- **R2** serves encoded audio.
- **Workflows** coordinate external song generation callbacks.
- **Modal** runs the ACE-Step GPU generator, encodes the final `.m4a`, uploads it to R2, and calls back into Cloudflare.

## Repository Layout

```text
client/       Static Next.js frontend
cloudflare/   Worker API, Durable Object, Workflow, D1 migrations
modal/        Modal generator service wired directly to the Cloudflare workflow
```

## Cloudflare Runtime

### Public API

- `POST /api/session/bootstrap`
- `GET /api/state`
- `POST /api/vote`

### Internal API

- `POST /internal/generation/callback`
- `POST /internal/seed`

### State Ownership

`StationControl` is the single writer for:

- current song
- next song
- active poll options/tallies
- per-session vote dedupe
- active listener presence
- scheduled vote-close and song-end events

## Local Development

### Client

```bash
cd client
bun install
bun run build
```

### Cloudflare Runtime

```bash
cd cloudflare
npm install
npm run check
```

Render `cloudflare/wrangler.jsonc` from the template before deploying:

```bash
node scripts/render-config.mjs wrangler.jsonc
```

Required environment variables are described in the GitHub Actions workflow and the `cloudflare/wrangler.template.jsonc` placeholders.

### Modal Generator

```bash
cd modal
pip install -e .
modal deploy pulsefm_worker/app.py
```

The Modal runtime expects a secret named `pulsefm-modal-runtime` that provides:

- `MODAL_WEBHOOK_TOKEN`
- `R2_ENDPOINT_URL`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `PUBLIC_AUDIO_BASE_URL`
- optional `R2_REGION` and `ENCODED_CACHE_CONTROL`

## Deployment

Deployment is handled by GitHub Actions:

- `ci.yml` validates the client build and Cloudflare TypeScript runtime.
- `deploy.yml` renders Wrangler config, applies D1 migrations, deploys the Worker, and deploys the static Pages bundle.
- `modal-deploy.yml` deploys the Modal app on pushes to `main` when files under `modal/` change.

The deploy pipeline expects Cloudflare credentials, the generator auth token, and the Modal deploy tokens to be supplied as GitHub secrets.
