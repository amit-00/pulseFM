resource "google_cloud_run_v2_service" "vote_api" {
  name     = "vote-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.vote_api.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.vote_api_image
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "LOCATION"
        value = var.region
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.memorystore.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.memorystore.port)
      }
      env {
        name  = "TALLY_FUNCTION_URL"
        value = google_cloudfunctions2_function.tally_function.service_config[0].uri
      }
      env {
        name  = "VOTE_QUEUE_NAME"
        value = google_cloud_tasks_queue.tally_queue.name
      }
      env {
        name  = "TASKS_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.vote_api.email
      }
      env {
        name  = "ENCODED_BUCKET"
        value = "pulsefm-generated-songs"
      }
      env {
        name  = "ENCODED_PREFIX"
        value = "encoded/"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service" "encoder" {
  name     = "encoder"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.encoder.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.encoder_image
      env {
        name  = "RAW_BUCKET"
        value = "pulsefm-generated-songs"
      }
      env {
        name  = "RAW_PREFIX"
        value = "raw/"
      }
      env {
        name  = "ENCODED_BUCKET"
        value = "pulsefm-generated-songs"
      }
      env {
        name  = "ENCODED_PREFIX"
        value = "encoded/"
      }
      env {
        name  = "ENCODED_CACHE_CONTROL"
        value = "public,max-age=300,s-maxage=3600"
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.memorystore.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.memorystore.port)
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service" "playback_service" {
  name     = "playback-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.playback_service.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.playback_service_image
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "LOCATION"
        value = var.region
      }
      env {
        name  = "STATIONS_COLLECTION"
        value = "stations"
      }
      env {
        name  = "SONGS_COLLECTION"
        value = "songs"
      }
      env {
        name  = "VOTE_STATE_COLLECTION"
        value = "voteState"
      }
      env {
        name  = "VOTE_EVENTS_TOPIC"
        value = google_pubsub_topic.vote_events.name
      }
      env {
        name  = "WINDOW_SECONDS"
        value = tostring(var.window_seconds)
      }
      env {
        name  = "OPTIONS_PER_WINDOW"
        value = tostring(var.options_per_window)
      }
      env {
        name  = "PLAYBACK_QUEUE_NAME"
        value = google_cloud_tasks_queue.playback_queue.name
      }
      env {
        name  = "PLAYBACK_EVENTS_TOPIC"
        value = google_pubsub_topic.playback_events.name
      }
      env {
        name  = "PLAYBACK_TICK_URL"
        value = "https://playback-service${local.cloud_run_url_suffix}"
      }
      env {
        name  = "TASKS_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.playback_service.email
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.memorystore.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.memorystore.port)
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service" "playback_stream" {
  name     = "playback-stream"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.playback_stream.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.playback_stream_image
      env {
        name  = "STATIONS_COLLECTION"
        value = "stations"
      }
      env {
        name  = "VOTE_STATE_COLLECTION"
        value = "voteState"
      }
      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.memorystore.host
      }
      env {
        name  = "REDIS_PORT"
        value = tostring(google_redis_instance.memorystore.port)
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service_iam_member" "vote_api_nextjs_invoker" {
  name     = google_cloud_run_v2_service.vote_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.nextjs_server.email}"
}

resource "google_cloud_run_v2_service_iam_member" "playback_stream_public" {
  name     = google_cloud_run_v2_service.playback_stream.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "eventarc_invoker" {
  name     = google_cloud_run_v2_service.encoder.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_cloud_run_v2_service_iam_member" "playback_service_invoker" {
  name     = google_cloud_run_v2_service.playback_service.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.playback_service.email}"
}
