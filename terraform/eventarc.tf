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
