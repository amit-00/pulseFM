locals {
  services = [
    "cloudresourcemanager.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "cloudtasks.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "services" {
  for_each = toset(local.services)
  project  = var.project_id
  service  = each.value

  disable_on_destroy = false
}
