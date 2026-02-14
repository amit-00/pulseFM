resource "google_pubsub_topic" "vote_events" {
  name = "vote-events"
}

resource "google_pubsub_topic" "playback_events" {
  name = "playback"
}
