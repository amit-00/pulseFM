# PulseFM Cloudflare Runtime

This package contains the migrated backend for PulseFM.

## Components

- `src/index.ts`: Worker entrypoint and HTTP routing
- `src/station-control.ts`: `StationControl` Durable Object
- `src/workflow.ts`: external generation workflow
- `migrations/`: D1 schema
- `wrangler.template.jsonc`: deploy template rendered by CI

## Required Config Values

These values are injected when rendering `wrangler.jsonc`:

- app origin
- API/public routes
- D1 database id
- R2 bucket name
- audio base URL
- external generator URL

## Runtime Secrets

These secrets are platform-owned and should be provisioned directly in Cloudflare for each Worker environment instead of coming from GitHub Actions:

- `EXTERNAL_GENERATOR_TOKEN`
- `SESSION_TOKEN_SECRET`
- `INTERNAL_CALLBACK_SECRET`

Set them with Wrangler before deploy:

```bash
wrangler secret put EXTERNAL_GENERATOR_TOKEN
wrangler secret put SESSION_TOKEN_SECRET
wrangler secret put INTERNAL_CALLBACK_SECRET
wrangler secret put EXTERNAL_GENERATOR_TOKEN --env preview
wrangler secret put SESSION_TOKEN_SECRET --env preview
wrangler secret put INTERNAL_CALLBACK_SECRET --env preview
```

The external generator is expected to accept `POST /jobs`, upload the final `encoded/{voteId}.m4a` object to R2, and complete the workflow by calling `POST /internal/generation/callback`.

## Deploy Steps

```bash
npm install
node scripts/render-config.mjs wrangler.jsonc
npx wrangler d1 migrations apply pulsefm --remote --config wrangler.jsonc
npx wrangler deploy --config wrangler.jsonc
```
