# Terraform (PulseFM)

This directory provisions Cloud Run services (vote-api, playback-service, encoder, playback-stream, modal-dispatch-service), Cloud Functions (tally-function, heartbeat-ingress, heartbeat-receiver, next-song-updater), Firestore, Cloud Tasks, Pub/Sub, GCS, Eventarc, IAM, Artifact Registry, Memorystore (Redis), and an external HTTPS load balancer + Cloud CDN for audio delivery.

## Prereqs
- GCS bucket for Terraform state: `pulsefm-terraform-state`
- GitHub repository connected to Cloud Build (for the trigger)

## Inputs (required)
- `vote_api_image`, `playback_service_image`, `playback_stream_image`, `modal_dispatch_service_image`, `encoder_image`
- `github_owner`, `github_repo`
- `cdn_signed_cookie_key_value`
- `nextjs_session_signing_key`

## Usage
```
cd terraform
terraform init
terraform apply \
  -var="vote_api_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-api:placeholder" \
  -var="encoder_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/encoder:placeholder" \
  -var="playback_service_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-service:placeholder" \
  -var="playback_stream_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-stream:placeholder" \
  -var="modal_dispatch_service_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/modal-dispatch-service:placeholder" \
  -var="github_owner=<owner>" \
  -var="github_repo=<repo>"
```

After the trigger is created (it is disabled by default), run it manually in Cloud Build. It will apply Terraform, build/push images, and deploy Cloud Run by digest.

## Vercel OIDC (production only)
- Terraform provisions a Workload Identity Pool + Provider for the Vercel team issuer.
- Impersonation is restricted to subject: `owner:amit00s-projects:project:pulse-fm:environment:production`.
- The following Terraform outputs should be set in Vercel for the server app:
  - `project_number`
  - `nextjs_server_service_account`
  - `vercel_wif_pool_id`
  - `vercel_wif_provider_id`
- Keep these Vercel-side values aligned with Terraform defaults unless intentionally overridden:
  - issuer: `https://oidc.vercel.com/amit00s-projects`
  - audience: `https://vercel.com/amit00s-projects`

## CDN notes
- CDN hostname defaults to `cdn.pulsefm.fm`.
- Terraform creates a Cloud DNS managed zone for `cdn.pulsefm.fm.` and publishes the A record.
- If your parent DNS is managed elsewhere, delegate `cdn.pulsefm.fm` to the `cdn_dns_nameservers` output nameservers.
