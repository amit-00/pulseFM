resource "google_eventarc_trigger" "encoder_finalize" {
  provider = google-beta

  name     = "encoder-finalize"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }

  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.generated_songs.name
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.encoder.name
      region  = var.region
    }
  }

  service_account = google_service_account.eventarc.email
}

resource "google_eventarc_trigger" "playback_stream_tally" {
  provider = google-beta

  name     = "playback-stream-tally"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.tally_events.id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.playback_stream.name
      region  = var.region
      path    = "/events/tally"
    }
  }

  service_account = google_service_account.eventarc.email
}

resource "google_eventarc_trigger" "playback_stream_changeover" {
  provider = google-beta

  name     = "playback-stream-changeover"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.playback_events.id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.playback_stream.name
      region  = var.region
      path    = "/events/playback"
    }
  }

  service_account = google_service_account.eventarc.email
}

resource "google_eventarc_trigger" "playback_stream_vote_events" {
  provider = google-beta

  name     = "playback-stream-vote-events"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.vote_events.id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.playback_stream.name
      region  = var.region
      path    = "/events/vote"
    }
  }

  service_account = google_service_account.eventarc.email
}

resource "google_eventarc_trigger" "modal_dispatch_vote_events" {
  provider = google-beta

  name     = "modal-dispatch-vote-events"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.vote_events.id
    }
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.modal_dispatch_service.name
      region  = var.region
      path    = "/events/vote"
    }
  }

  service_account = google_service_account.eventarc.email
}
