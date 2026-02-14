resource "google_pubsub_topic" "vote_events" {
  name = "vote-events"
}

resource "google_pubsub_topic" "playback_events" {
  name = "playback"
}

resource "google_pubsub_topic" "tally_events" {
  name = "tally"
}
