resource "google_storage_bucket" "generated_songs" {
  name          = "pulsefm-generated-songs"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["http://localhost:3000", "http://127.0.0.1:3000", "https://pulsefm.app", "https://www.pulsefm.app"]
    method          = ["GET", "HEAD", "OPTIONS"]
    response_header = ["Content-Type", "Content-Length", "Accept-Ranges", "Range"]
    max_age_seconds = 3600
  }
}

resource "google_storage_bucket" "functions_source" {
  name          = "${var.project_id}-functions"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
}
