# PulseFM Client

Static Next.js frontend for PulseFM, exported for Cloudflare Pages.

## Runtime Environment

These values are consumed at build time:

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | optional | Base URL for the Cloudflare API. Leave empty for same-origin `/api` routing. |
| `NEXT_PUBLIC_AUDIO_BASE_URL` | optional | Public base URL for encoded audio objects when the snapshot omits `audioUrl`. |
| `NEXT_PUBLIC_SITE_URL` | optional | Canonical site URL used for metadata generation. |

## Session Model

- The client bootstraps an anonymous session token from `POST /api/session/bootstrap`.
- The token is stored in `localStorage` and attached to subsequent API calls.
- Vote memory is also stored locally so multiple tabs can reuse the current vote selection state.

## Runtime Flow

- The app polls `GET /api/state` every 3 seconds.
- Vote submission uses `POST /api/vote`.
- Playback continuity is reconciled locally by comparing the latest snapshot to the previously loaded song state.

## Build

```bash
npm install
npm run build
```

The build outputs a static export in `client/out`, which is the artifact deployed to Cloudflare Pages.
