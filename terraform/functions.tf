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

    environment_variables = {
      VOTE_STATE_COLLECTION = "voteState"
      VOTES_COLLECTION      = "votes"
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
