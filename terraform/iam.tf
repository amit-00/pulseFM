data "google_project" "current" {}

resource "google_project_iam_member" "vote_api_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_project_iam_member" "tally_function_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.tally_function.email}"
}

resource "google_project_iam_member" "tally_function_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.tally_function.email}"
}

resource "google_project_iam_member" "modal_dispatcher_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.modal_dispatcher.email}"
}

resource "google_project_iam_member" "playback_stream_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.playback_stream.email}"
}

resource "google_project_iam_member" "playback_service_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.playback_service.email}"
}

resource "google_project_iam_member" "playback_service_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.playback_service.email}"
}

resource "google_project_iam_member" "playback_service_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.playback_service.email}"
}

resource "google_project_iam_member" "eventarc_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.eventarc.email}"
}

resource "google_project_iam_member" "vote_api_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_project_iam_member" "vote_api_vpc_access" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_project_iam_member" "playback_service_vpc_access" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${google_service_account.playback_service.email}"
}

resource "google_project_iam_member" "playback_stream_vpc_access" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${google_service_account.playback_stream.email}"
}

resource "google_project_iam_member" "encoder_vpc_access" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${google_service_account.encoder.email}"
}

resource "google_project_iam_member" "tally_function_vpc_access" {
  project = var.project_id
  role    = "roles/vpcaccess.user"
  member  = "serviceAccount:${google_service_account.tally_function.email}"
}

resource "google_project_iam_member" "encoder_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.encoder.email}"
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

resource "google_storage_bucket_iam_member" "cdn_bucket_reader" {
  bucket = google_storage_bucket.generated_songs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:service-${data.google_project.current.number}@cloud-cdn-fill.iam.gserviceaccount.com"

  # The Cloud CDN fill service agent is auto-provisioned when CDN is first
  # enabled on a backend bucket.  Ensure that resource exists before the binding.
  depends_on = [google_compute_backend_bucket.audio_cdn]
}

resource "google_storage_bucket_iam_member" "functions_source_reader" {
  bucket = google_storage_bucket.functions_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:service-${data.google_project.current.number}@gcf-admin-robot.iam.gserviceaccount.com"
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

resource "google_project_iam_member" "terraform_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_vote_api" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_tally_function" {
  service_account_id = google_service_account.tally_function.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_modal_dispatcher" {
  service_account_id = google_service_account.modal_dispatcher.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_encoder" {
  service_account_id = google_service_account.encoder.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_playback_service" {
  service_account_id = google_service_account.playback_service.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "terraform_act_as_playback_stream" {
  service_account_id = google_service_account.playback_stream.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.terraform.email}"
}

resource "google_service_account_iam_member" "cloudbuild_impersonate_terraform" {
  service_account_id = google_service_account.terraform.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:cloud-build-deployer@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "cloudtasks_token_creator" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
}

resource "google_service_account_iam_member" "cloudtasks_token_creator_playback" {
  service_account_id = google_service_account.playback_service.name
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

resource "google_service_account_iam_member" "vote_api_act_as_self" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_storage_bucket_iam_member" "vote_api_bucket_viewer" {
  bucket = google_storage_bucket.generated_songs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_service_account_iam_member" "vote_api_sign_blobs" {
  service_account_id = google_service_account.vote_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.vote_api.email}"
}

resource "google_service_account_iam_member" "playback_service_act_as_self" {
  service_account_id = google_service_account.playback_service.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.playback_service.email}"
}
