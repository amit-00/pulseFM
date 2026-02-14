project_id    = "pulsefm-484500"
region        = "northamerica-northeast1"
artifact_repo = "pulsefm"

# Placeholder images for initial apply
vote_api_image              = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-api:bootstrap"
encoder_image               = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/encoder:bootstrap"
playback_service_image      = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-service:bootstrap"
playback_stream_image       = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-stream:bootstrap"

# Secrets / config

window_seconds     = 300
options_per_window = 4

# Cloud Build trigger repo info
github_owner  = "amit-00"
github_repo   = "pulseFM"
github_branch = "main"
