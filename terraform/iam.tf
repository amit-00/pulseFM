data "google_project" "current" {}

resource "google_project_iam_member" "vote_api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_project_iam_member" "tally_worker_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.tally_worker.email}"
}

resource "google_project_iam_member" "vote_orchestrator_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.vote_orchestrator.email}"
}

resource "google_project_iam_member" "vote_api_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_storage_bucket_iam_member" "encoder_bucket_access" {
  bucket = google_storage_bucket.generated_songs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.encoder.email}"
}

resource "google_storage_bucket_iam_member" "eventarc_bucket_reader" {
  bucket = google_storage_bucket.generated_songs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_project_iam_member" "eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_project_iam_member" "terraform_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_vote_api" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_tally_worker" {
  service_account_id = google_service_account.tally_worker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_vote_orchestrator" {
  service_account_id = google_service_account.vote_orchestrator.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_encoder" {
  service_account_id = google_service_account.encoder.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "cloudbuild_impersonate_terraform" {
  service_account_id = google_service_account.terraform.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

resource "google_service_account_iam_member" "cloudtasks_token_creator" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}


resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gs-project-accounts.iam.gserviceaccount.com"
}
