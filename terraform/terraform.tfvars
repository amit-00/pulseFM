project_id    = "pulsefm-484500"
region        = "northamerica-northeast1"
artifact_repo = "pulsefm"

# Placeholder images for initial apply
vote_api_image              = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-api:bootstrap"
vote_orchestrator_image     = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-orchestrator:bootstrap"
encoder_image               = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/encoder:bootstrap"
playback_orchestrator_image = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/playback-orchestrator:bootstrap"
vote_stream_image           = "northamerica-northeast1-docker.pkg.dev/pulsefm-484500/pulsefm/vote-stream:bootstrap"

# Secrets / config
session_jwt_secret = "KZfr62k0f7xUrl49M3sDAaMe8cCf+UCc4A62sz+qzUo="

window_seconds     = 300
options_per_window = 4

# Cloud Build trigger repo info
github_owner  = "amit-00"
github_repo   = "pulseFM"
github_branch = "main"
