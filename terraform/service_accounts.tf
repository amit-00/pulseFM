resource "google_service_account" "vote_api" {
  account_id   = "vote-api"
  display_name = "vote-api"
}

resource "google_service_account" "tally_function" {
  account_id   = "tally-function"
  display_name = "tally-function"
}

resource "google_service_account" "modal_dispatcher" {
  account_id   = "modal-dispatcher"
  display_name = "modal-dispatcher"
}

resource "google_service_account" "playback_service" {
  account_id   = "playback-service"
  display_name = "playback-service"
}

resource "google_service_account" "encoder" {
  account_id   = "encoder"
  display_name = "encoder"
}

resource "google_service_account" "vote_stream" {
  account_id   = "vote-stream"
  display_name = "vote-stream"
}

resource "google_service_account" "eventarc" {
  account_id   = "eventarc"
  display_name = "eventarc"
}

resource "google_service_account" "terraform" {
  account_id   = "terraform"
  display_name = "terraform"
}
