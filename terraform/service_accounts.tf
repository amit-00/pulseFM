resource "google_service_account" "vote_api" {
  account_id   = "vote-api"
  display_name = "vote-api"
}

resource "google_service_account" "tally_function" {
  account_id   = "tally-function"
  display_name = "tally-function"
}

resource "google_service_account" "vote_orchestrator" {
  account_id   = "vote-orchestrator"
  display_name = "vote-orchestrator"
}

resource "google_service_account" "encoder" {
  account_id   = "encoder"
  display_name = "encoder"
}

resource "google_service_account" "playback_orchestrator" {
  account_id   = "playback-orchestrator"
  display_name = "playback-orchestrator"
}

resource "google_service_account" "eventarc" {
  account_id   = "eventarc"
  display_name = "eventarc"
}

resource "google_service_account" "terraform" {
  account_id   = "terraform"
  display_name = "terraform"
}
