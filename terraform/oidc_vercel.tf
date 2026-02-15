locals {
  vercel_oidc_subject = "owner:${var.vercel_team_slug}:project:${var.vercel_project_slug}:environment:${var.vercel_oidc_environment}"
}

resource "google_iam_workload_identity_pool" "vercel" {
  provider                  = google-beta
  workload_identity_pool_id = "vercel-oidc"
  display_name              = "Vercel OIDC"
  description               = "Federated identity pool for Vercel deployments."
}

resource "google_iam_workload_identity_pool_provider" "vercel" {
  provider                           = google-beta
  workload_identity_pool_id          = google_iam_workload_identity_pool.vercel.workload_identity_pool_id
  workload_identity_pool_provider_id = "vercel-team"
  display_name                       = "Vercel Team OIDC"
  description                        = "Trusts OIDC tokens from the configured Vercel team issuer."

  oidc {
    issuer_uri        = var.vercel_oidc_issuer_url
    allowed_audiences = [var.vercel_oidc_audience]
  }

  attribute_mapping = {
    "google.subject" = "assertion.sub"
  }
}

resource "google_service_account_iam_member" "nextjs_server_wif_user" {
  service_account_id = google_service_account.nextjs_server.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/projects/${data.google_project.current.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.vercel.workload_identity_pool_id}/subject/${local.vercel_oidc_subject}"
}
