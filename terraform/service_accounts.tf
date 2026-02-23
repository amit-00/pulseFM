resource "google_service_account" "vote_api" {
  account_id   = "vote-api"
  display_name = "vote-api"
}

resource "google_service_account" "tally_function" {
  account_id   = "tally-function"
  display_name = "tally-function"
}

resource "google_service_account" "modal_dispatch_service" {
  account_id   = "modal-dispatch-service"
  display_name = "modal-dispatch-service"
}

resource "google_service_account" "modal_worker" {
  account_id   = "modal-worker"
  display_name = "modal-worker"
}

resource "google_service_account" "heartbeat_ingress" {
  account_id   = "heartbeat-ingress"
  display_name = "heartbeat-ingress"
}

resource "google_service_account" "heartbeat_receiver" {
  account_id   = "heartbeat-receiver"
  display_name = "heartbeat-receiver"
}

resource "google_service_account" "next_song_updater" {
  account_id   = "next-song-updater"
  display_name = "next-song-updater"
}

resource "google_service_account" "playback_service" {
  account_id   = "playback-service"
  display_name = "playback-service"
}

resource "google_service_account" "encoder" {
  account_id   = "encoder"
  display_name = "encoder"
}

resource "google_service_account" "playback_stream" {
  account_id   = "playback-stream"
  display_name = "playback-stream"
}

resource "google_service_account" "nextjs_server" {
  account_id   = "nextjs-server"
  display_name = "nextjs-server"
}

resource "google_service_account" "eventarc" {
  account_id   = "eventarc"
  display_name = "eventarc"
}

resource "google_service_account" "terraform" {
  account_id   = "terraform"
  display_name = "terraform"
}
