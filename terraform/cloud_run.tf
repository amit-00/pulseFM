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
        name  = "SESSION_JWT_SECRET"
        value = var.session_jwt_secret
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

resource "google_cloud_run_v2_service" "vote_orchestrator" {
  name     = "vote-orchestrator"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.vote_orchestrator.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.vote_orchestrator_image
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "LOCATION"
        value = var.region
      }
      env {
        name  = "VOTE_STATE_COLLECTION"
        value = "voteState"
      }
      env {
        name  = "VOTE_WINDOWS_COLLECTION"
        value = "voteWindows"
      }
      env {
        name  = "VOTE_EVENTS_TOPIC"
        value = google_pubsub_topic.vote_events.name
      }
      env {
        name  = "VOTE_ORCHESTRATOR_QUEUE"
        value = google_cloud_tasks_queue.vote_orchestrator_queue.name
      }
      env {
        name  = "VOTE_ORCHESTRATOR_URL"
        value = "https://vote-orchestrator${local.cloud_run_url_suffix}"
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
        name  = "TASKS_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.vote_orchestrator.email
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

locals {
  # All Cloud Run services in the same project/region share the same URL suffix.
  # Extract it from vote_api (which has no self-reference issues).
  cloud_run_url_suffix = replace(
    google_cloud_run_v2_service.vote_api.uri,
    "https://vote-api",
    ""
  )
}

resource "google_cloud_run_v2_service" "playback_orchestrator" {
  name     = "playback-orchestrator"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.playback_orchestrator.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.playback_orchestrator_image
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
        name  = "VOTE_ORCHESTRATOR_QUEUE"
        value = google_cloud_tasks_queue.vote_orchestrator_queue.name
      }
      env {
        name  = "VOTE_ORCHESTRATOR_URL"
        value = google_cloud_run_v2_service.vote_orchestrator.uri
      }
      env {
        name  = "PLAYBACK_QUEUE_NAME"
        value = google_cloud_tasks_queue.playback_queue.name
      }
      env {
        name  = "PLAYBACK_TICK_URL"
        value = "https://playback-orchestrator${local.cloud_run_url_suffix}"
      }
      env {
        name  = "TASKS_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.playback_orchestrator.email
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

resource "google_cloud_run_v2_service" "vote_stream" {
  name     = "vote-stream"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.vote_stream.email
    vpc_access {
      connector = google_vpc_access_connector.memorystore.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.vote_stream_image
      env {
        name  = "SESSION_JWT_SECRET"
        value = var.session_jwt_secret
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

resource "google_cloud_run_v2_service_iam_member" "vote_api_public" {
  name     = google_cloud_run_v2_service.vote_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "vote_stream_public" {
  name     = google_cloud_run_v2_service.vote_stream.name
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

resource "google_cloud_run_v2_service_iam_member" "vote_orchestrator_invoker" {
  name     = google_cloud_run_v2_service.vote_orchestrator.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.playback_orchestrator.email}"
}

resource "google_cloud_run_v2_service_iam_member" "vote_orchestrator_self_invoker" {
  name     = google_cloud_run_v2_service.vote_orchestrator.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.vote_orchestrator.email}"
}

resource "google_cloud_run_v2_service_iam_member" "playback_orchestrator_invoker" {
  name     = google_cloud_run_v2_service.playback_orchestrator.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.playback_orchestrator.email}"
}
