# Terraform (PulseFM)

This directory provisions Cloud Run services (vote-api, vote-orchestrator, encoder, playback-orchestrator), a Cloud Function (tally-function), Firestore, Cloud Tasks, GCS, Eventarc, IAM, Artifact Registry, and Memorystore (Redis).

## Prereqs
- GCS bucket for Terraform state: `pulsefm-terraform-state`
- GitHub repository connected to Cloud Build (for the trigger)

## Inputs (required)
- `session_jwt_secret`
- `vote_api_image`, `vote_orchestrator_image`, `encoder_image`, `playback_orchestrator_image`
- `github_owner`, `github_repo`

## Usage
```
cd terraform
terraform init
terraform apply \
  -var="session_jwt_secret=..." \
  -var="vote_api_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-api:placeholder" \
  -var="vote_orchestrator_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-orchestrator:placeholder" \
  -var="encoder_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/encoder:placeholder" \
  -var="playback_orchestrator_image=northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-orchestrator:placeholder" \
  -var="github_owner=<owner>" \
  -var="github_repo=<repo>"
```

After the trigger is created (it is disabled by default), run it manually in Cloud Build. It will apply Terraform, build/push images, and deploy Cloud Run by digest.
