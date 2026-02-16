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
    available_memory              = "256M"
    timeout_seconds               = 60
    ingress_settings              = "ALLOW_ALL"
    service_account_email         = google_service_account.tally_function.email
    vpc_connector                 = google_vpc_access_connector.memorystore.id
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"

    environment_variables = {
      PROJECT_ID  = var.project_id
      TALLY_TOPIC = google_pubsub_topic.tally_events.name
      REDIS_HOST  = google_redis_instance.memorystore.host
      REDIS_PORT  = tostring(google_redis_instance.memorystore.port)
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

resource "google_cloud_run_v2_service_iam_member" "tally_function_run_invoker" {
  name     = google_cloudfunctions2_function.tally_function.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.vote_api.email}"
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
    available_memory              = "256M"
    timeout_seconds               = 60
    service_account_email         = google_service_account.modal_dispatcher.email
    vpc_connector                 = google_vpc_access_connector.memorystore.id
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"

    environment_variables = {
      REDIS_HOST = google_redis_instance.memorystore.host
      REDIS_PORT = tostring(google_redis_instance.memorystore.port)
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.vote_events.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }
}

data "archive_file" "heartbeat_ingress" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/heartbeat-ingress"
  output_path = "${path.module}/.tmp/heartbeat-ingress.zip"
}

resource "google_storage_bucket_object" "heartbeat_ingress_source" {
  name   = "heartbeat-ingress-${data.archive_file.heartbeat_ingress.output_md5}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.heartbeat_ingress.output_path
}

resource "google_cloudfunctions2_function" "heartbeat_ingress" {
  name     = "heartbeat-ingress"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "heartbeat_ingress"

    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.heartbeat_ingress_source.name
      }
    }
  }

  service_config {
    available_memory      = "256M"
    timeout_seconds       = 30
    ingress_settings      = "ALLOW_ALL"
    service_account_email = google_service_account.heartbeat_ingress.email

    environment_variables = {
      PROJECT_ID      = var.project_id
      HEARTBEAT_TOPIC = google_pubsub_topic.heartbeat_events.name
    }
  }
}

resource "google_cloudfunctions2_function_iam_member" "heartbeat_ingress_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.heartbeat_ingress.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_service_account.nextjs_server.email}"
}

resource "google_cloud_run_v2_service_iam_member" "heartbeat_ingress_run_invoker" {
  name     = google_cloudfunctions2_function.heartbeat_ingress.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.nextjs_server.email}"
}

data "archive_file" "heartbeat_receiver" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/heartbeat-receiver"
  output_path = "${path.module}/.tmp/heartbeat-receiver.zip"
}

resource "google_storage_bucket_object" "heartbeat_receiver_source" {
  name   = "heartbeat-receiver-${data.archive_file.heartbeat_receiver.output_md5}.zip"
  bucket = google_storage_bucket.functions_source.name
  source = data.archive_file.heartbeat_receiver.output_path
}

resource "google_cloudfunctions2_function" "heartbeat_receiver" {
  name     = "heartbeat-receiver"
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "heartbeat_receiver"

    source {
      storage_source {
        bucket = google_storage_bucket.functions_source.name
        object = google_storage_bucket_object.heartbeat_receiver_source.name
      }
    }
  }

  service_config {
    available_memory              = "256M"
    timeout_seconds               = 30
    service_account_email         = google_service_account.heartbeat_receiver.email
    vpc_connector                 = google_vpc_access_connector.memorystore.id
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"

    environment_variables = {
      REDIS_HOST            = google_redis_instance.memorystore.host
      REDIS_PORT            = tostring(google_redis_instance.memorystore.port)
      HEARTBEAT_TTL_SECONDS = "30"
    }
  }

  event_trigger {
    trigger_region = var.region
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.heartbeat_events.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }
}
