# PulseFM Modal Generator

This app owns external song generation for the Cloudflare runtime.

## Responsibilities

- accept `POST /jobs` requests from the Cloudflare workflow
- generate the song with ACE-Step on Modal
- encode the final artifact as `.m4a` using the legacy encoder settings
- upload `encoded/{voteId}.m4a` directly to R2
- call `POST /internal/generation/callback` on the Cloudflare Worker

## Deploy

Run deploy commands from the `modal/` directory so the local `modal` folder does not shadow the installed Modal package:

```bash
pip install -e .
modal deploy pulsefm_worker/app.py
```

## Required Modal Secret

Create a Modal secret named `pulsefm-modal-runtime` with:

- `MODAL_WEBHOOK_TOKEN` (same value as Cloudflare `EXTERNAL_GENERATOR_TOKEN`)
- `R2_ENDPOINT_URL`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `PUBLIC_AUDIO_BASE_URL`
- optional `R2_REGION`
- optional `ENCODED_CACHE_CONTROL`
- optional `CALLBACK_TIMEOUT_SEC`
