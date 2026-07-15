resource "google_secret_manager_secret" "nextjs_session_signing_key" {
  secret_id = "nextjs-session-signing-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "nextjs_session_signing_key" {
  secret      = google_secret_manager_secret.nextjs_session_signing_key.id
  secret_data = var.nextjs_session_signing_key
}

resource "google_secret_manager_secret_iam_member" "nextjs_session_signing_key_accessor" {
  secret_id = google_secret_manager_secret.nextjs_session_signing_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.nextjs_server.email}"
}

resource "google_secret_manager_secret" "modal_token_id" {
  secret_id = "modal-token-id"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "modal_token_id" {
  secret      = google_secret_manager_secret.modal_token_id.id
  secret_data = var.modal_token_id
}

resource "google_secret_manager_secret_iam_member" "modal_token_id_accessor" {
  secret_id = google_secret_manager_secret.modal_token_id.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.modal_dispatch_service.email}"
}

resource "google_secret_manager_secret" "modal_token_secret" {
  secret_id = "modal-token-secret"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "modal_token_secret" {
  secret      = google_secret_manager_secret.modal_token_secret.id
  secret_data = var.modal_token_secret
}

resource "google_secret_manager_secret_iam_member" "modal_token_secret_accessor" {
  secret_id = google_secret_manager_secret.modal_token_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.modal_dispatch_service.email}"
}
