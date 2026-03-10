This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Runtime env vars

- `VOTE_API_URL`: Cloud Run URL for `vote-api`.
- `HEARTBEAT_INGRESS_URL`: Cloud Function Gen2 URL for heartbeat ingress.
- `PLAYBACK_STREAM_URL`: Cloud Run URL for `playback-stream` (used by `/api/playback/state` and `/api/playback/stream` proxy routes).
- `AUTH_SECRET`: Auth.js JWT signing secret (or `NEXTAUTH_SECRET`).
- `GCP_PROJECT_ID`: GCP project id used for Workload Identity Federation.
- `GCP_PROJECT_NUMBER`: GCP project number used to build WIF audience.
- `GCP_SERVICE_ACCOUNT_EMAIL`: Service account email to impersonate (nextjs-server SA).
- `GCP_WORKLOAD_IDENTITY_POOL_ID`: Workload Identity Pool id.
- `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID`: Workload Identity Pool Provider id.
- `UPSTASH_REDIS_REST_URL`: Upstash Redis REST endpoint URL.
- `UPSTASH_REDIS_REST_TOKEN`: Upstash Redis REST auth token.
- `NEXT_PUBLIC_CDN_BASE_URL`: Preferred base URL for audio objects (for example `https://cdn.pulsefm.fm`).
- `NEXT_PUBLIC_BUCKET_BASE_URL`: Fallback base URL when CDN URL is unset (default: `https://storage.googleapis.com/pulsefm-generated-songs`).

## Session bootstrap

- `POST /api/session` with JSON payload `{ "name": "..." }`.
- Auth.js credentials provider creates a stateless JWT session.
- `proxy.ts` validates the session for all `/api/*` routes (except `/api/session` and `/api/auth/*`) and injects `X-Session-Id` from Auth.js `sub`.
- Server-side Cloud Run calls use explicit Vercel OIDC token exchange with GCP WIF (keyless).
- On initial app load, the client verifies session validity; if missing/invalid, it auto-bootstraps a session via `POST /api/session`.

## Proxy rate limits

- `/api/vote`: `10/min` and `60/hour` per session.
- `/api/heartbeat`: `6/min` per session.
- Limit responses return `429` with body `{ "error": "rate_limited", "retryAfterSec": <number> }` and `Retry-After` header.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
