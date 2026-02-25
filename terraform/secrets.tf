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
