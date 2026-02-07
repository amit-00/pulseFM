output "vote_api_url" {
  value = google_cloud_run_v2_service.vote_api.uri
}

output "tally_function_url" {
  value = google_cloudfunctions2_function.tally_function.service_config[0].uri
}

output "vote_orchestrator_url" {
  value = google_cloud_run_v2_service.vote_orchestrator.uri
}

output "encoder_url" {
  value = google_cloud_run_v2_service.encoder.uri
}

output "playback_orchestrator_url" {
  value = google_cloud_run_v2_service.playback_orchestrator.uri
}

output "tally_queue" {
  value = google_cloud_tasks_queue.tally_queue.name
}

output "vote_orchestrator_queue" {
  value = google_cloud_tasks_queue.vote_orchestrator_queue.name
}

output "playback_queue" {
  value = google_cloud_tasks_queue.playback_queue.name
}

output "bucket_name" {
  value = google_storage_bucket.generated_songs.name
}

output "artifact_repo" {
  value = google_artifact_registry_repository.pulsefm.repository_id
}

output "terraform_service_account" {
  value = google_service_account.terraform.email
}
