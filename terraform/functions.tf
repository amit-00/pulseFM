data "archive_file" "tally_function" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/tally-function"
  output_path = "${path.module}/.tmp/tally-function.zip"
}

resource "google_storage_bucket_object" "tally_function_source" {
  name   = "tally-function-${data.archive_file.tally_function.output_md5}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.tally_function.output_path
}

resource "google_cloudfunctions2_function" "tally_function" {
  name     = "tally-function"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "tally_function"

    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.tally_function_source.name
      }
    }
  }

  service_config {
    available_memory      = "256M"
    timeout_seconds       = 60
    ingress_settings      = "ALLOW_INTERNAL_ONLY"
    service_account_email = google_service_account.tally_function.email
    vpc_connector         = google_vpc_access_connector.memorystore.id
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"

    environment_variables = {
      REDIS_HOST = google_redis_instance.memorystore.host
      REDIS_PORT = tostring(google_redis_instance.memorystore.port)
    }
  }
}

resource "google_cloudfunctions2_function_iam_member" "tally_function_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.tally_function.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.vote_api.email}"
}

data "archive_file" "modal_dispatcher" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/modal-dispatcher"
  output_path = "${path.module}/.tmp/modal-dispatcher.zip"
}

resource "google_storage_bucket_object" "modal_dispatcher_source" {
  name   = "modal-dispatcher-${data.archive_file.modal_dispatcher.output_md5}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.modal_dispatcher.output_path
}

resource "google_cloudfunctions2_function" "modal_dispatcher" {
  name     = "modal-dispatcher"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "modal_dispatcher"

    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.modal_dispatcher_source.name
      }
    }
  }

  service_config {
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = google_service_account.modal_dispatcher.email

    environment_variables = {
      HEARTBEAT_COLLECTION = "heartbeat"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.vote_events.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }
}
