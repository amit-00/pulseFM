# Terraform (PulseFM)

This directory provisions Cloud Run services (vote-api, playback-service, encoder, playback-stream), Cloud Functions (tally-function, modal-dispatcher), Firestore, Cloud Tasks, Pub/Sub, GCS, Eventarc, IAM, Artifact Registry, and Memorystore (Redis).

## Prereqs
- GCS bucket for Terraform state: `pulsefm-terraform-state`
- GitHub repository connected to Cloud Build (for the trigger)

## Inputs (required)
- `session_jwt_secret`
- `vote_api_image`, `playback_service_image`, `playback_stream_image`, `encoder_image`
- `github_owner`, `github_repo`

## Usage
```
cd terraform
terraform init
terraform apply \
  -var="session_jwt_secret=..." \
  -var="vote_api_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-api:placeholder" \
  -var="encoder_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/encoder:placeholder" \
  -var="playback_service_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-service:placeholder" \
  -var="playback_stream_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-stream:placeholder" \
  -var="github_owner=<owner>" \
  -var="github_repo=<repo>"
```

After the trigger is created (it is disabled by default), run it manually in Cloud Build. It will apply Terraform, build/push images, and deploy Cloud Run by digest.
