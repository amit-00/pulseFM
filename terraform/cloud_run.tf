resource "google_cloud_run_v2_service" "vote_api" {
  name     = "vote-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.vote_api.email
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
        name  = "SESSION_JWT_SECRET"
        value = var.session_jwt_secret
      }
      env {
        name  = "TALLY_WORKER_URL"
        value = google_cloud_run_v2_service.tally_worker.uri
      }
      env {
        name  = "VOTE_QUEUE_NAME"
        value = google_cloud_tasks_queue.vote_queue.name
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
        name  = "VOTES_COLLECTION"
        value = "votes"
      }
      env {
        name  = "TASKS_OIDC_SERVICE_ACCOUNT"
        value = google_service_account.vote_api.email
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service" "tally_worker" {
  name     = "tally-worker"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.tally_worker.email
    containers {
      image = var.tally_worker_image
      env {
        name  = "VOTE_STATE_COLLECTION"
        value = "voteState"
      }
      env {
        name  = "VOTES_COLLECTION"
        value = "votes"
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
    containers {
      image = var.vote_orchestrator_image
      env {
        name  = "VOTE_STATE_COLLECTION"
        value = "voteState"
      }
      env {
        name  = "VOTE_WINDOWS_COLLECTION"
        value = "voteWindows"
      }
      env {
        name  = "WINDOW_SECONDS"
        value = tostring(var.window_seconds)
      }
      env {
        name  = "OPTIONS_PER_WINDOW"
        value = tostring(var.options_per_window)
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
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.encoder.email
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

resource "google_cloud_run_v2_service_iam_member" "tally_worker_invoker" {
  name     = google_cloud_run_v2_service.tally_worker.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_cloud_run_v2_service_iam_member" "eventarc_invoker" {
  name     = google_cloud_run_v2_service.encoder.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc.email}"
}
