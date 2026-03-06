# Cloudflare Backend Boilerplate (Phase 1)

This repository now includes Cloudflare deployment scaffolding for **backend migration only**.

Phase 1 is intentionally limited to boilerplate:
- metadata-only Wrangler config,
- service secret templates,
- setup/validation scripts,
- GitHub Actions workflow scaffolding.

It does **not** create or deploy Workers, Pages, routes, KV, D1, R2, or queues.

## Directory layout

- `infra/cloudflare/wrangler.toml`: metadata-only Cloudflare config.
- `infra/cloudflare/.dev.vars.example`: non-secret local vars template.
- `infra/cloudflare/env/*.secrets.example`: per-service secret name templates.
- `scripts/cloudflare/whoami.sh`: auth check wrapper.
- `scripts/cloudflare/validate.sh`: boilerplate guardrails + Wrangler config validation.

## Local setup

1. Install Wrangler (`npm i -g wrangler@4`), or rely on `npx` fallback in scripts.
2. Authenticate:
   ```bash
   ./scripts/cloudflare/whoami.sh
   ```
3. Validate phase-1 boilerplate:
   ```bash
   ./scripts/cloudflare/validate.sh
   ```

## Cloudflare managed secrets

Use Cloudflare-managed secrets as the source of truth:

```bash
printf '%s' '<value>' | wrangler secret put PULSEFM_REDIS_URL --config infra/cloudflare/wrangler.toml
```

Repeat for keys listed in:
- `infra/cloudflare/env/common.secrets.example`
- `infra/cloudflare/env/vote-api.secrets.example`
- `infra/cloudflare/env/playback-service.secrets.example`
- `infra/cloudflare/env/playback-stream.secrets.example`
- `infra/cloudflare/env/encoder.secrets.example`
- `infra/cloudflare/env/modal-dispatch-service.secrets.example`

## GitHub Actions expectations

Create these repository secrets before enabling deployment workflows:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Optional repository variable for future activation:
- `ENABLE_CLOUDFLARE_BACKEND_DEPLOY=true`

The deploy workflow is intentionally scaffold-only in phase 1.
