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
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
    "redis.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
  ]

  # All Cloud Run services in the same project/region share the same URL suffix.
  # Extract it from vote_api (which has no self-reference issues).
  cloud_run_url_suffix = replace(
    google_cloud_run_v2_service.vote_api.uri,
    "https://vote-api",
    ""
  )
}
