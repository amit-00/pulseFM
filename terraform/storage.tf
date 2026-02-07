resource "google_storage_bucket" "generated_songs" {
  name          = "pulsefm-generated-songs"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "functions_source" {
  name          = "${var.project_id}-functions"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}
