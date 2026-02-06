resource "google_storage_bucket" "generated_songs" {
  name          = "pulsefm-generated-songs"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
}
