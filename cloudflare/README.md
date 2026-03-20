# PulseFM Cloudflare Runtime

This package contains the migrated backend for PulseFM.

## Components

- `src/index.ts`: Worker entrypoint and HTTP routing
- `src/station-control.ts`: `StationControl` Durable Object
- `src/workflow.ts`: external generation workflow
- `migrations/`: D1 schema
- `wrangler.template.jsonc`: deploy template rendered by CI

## Required Secrets

- `SESSION_TOKEN_SECRET`
- `INTERNAL_CALLBACK_SECRET`

## Required Config Values

These values are injected when rendering `wrangler.jsonc`:

- app origin
- API/public routes
- D1 database id
- R2 bucket name
- audio base URL
- external generator URL

## Deploy Steps

```bash
npm install
node scripts/render-config.mjs wrangler.jsonc
npx wrangler d1 migrations apply pulsefm --remote --config wrangler.jsonc
npx wrangler deploy --config wrangler.jsonc
```
