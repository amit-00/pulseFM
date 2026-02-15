resource "google_artifact_registry_repository" "pulsefm" {
  provider      = google
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
}
