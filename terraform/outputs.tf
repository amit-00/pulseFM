output "vote_api_url" {
  value = google_cloud_run_v2_service.vote_api.uri
}

output "tally_function_url" {
  value = google_cloudfunctions2_function.tally_function.service_config[0].uri
}

output "heartbeat_ingress_url" {
  value = google_cloudfunctions2_function.heartbeat_ingress.service_config[0].uri
}

output "next_song_updater_url" {
  value = google_cloudfunctions2_function.next_song_updater.service_config[0].uri
}

output "encoder_url" {
  value = google_cloud_run_v2_service.encoder.uri
}

output "playback_service_url" {
  value = google_cloud_run_v2_service.playback_service.uri
}

output "playback_stream_url" {
  value = google_cloud_run_v2_service.playback_stream.uri
}

output "modal_dispatch_service_url" {
  value = google_cloud_run_v2_service.modal_dispatch_service.uri
}

output "tally_queue" {
  value = google_cloud_tasks_queue.tally_queue.name
}

output "playback_queue" {
  value = google_cloud_tasks_queue.playback_queue.name
}

output "modal_dispatch_queue" {
  value = google_cloud_tasks_queue.modal_dispatch_queue.name
}

output "bucket_name" {
  value = google_storage_bucket.generated_songs.name
}

output "artifact_repo" {
  value = google_artifact_registry_repository.pulsefm.repository_id
}

output "memorystore_host" {
  value = google_redis_instance.memorystore.host
}

output "memorystore_port" {
  value = google_redis_instance.memorystore.port
}

output "memorystore_network" {
  value = google_compute_network.memorystore.name
}

output "memorystore_connector" {
  value = google_vpc_access_connector.memorystore.name
}

output "terraform_service_account" {
  value = google_service_account.terraform.email
}

output "nextjs_server_service_account" {
  value = google_service_account.nextjs_server.email
}

output "modal_worker_service_account" {
  value = google_service_account.modal_worker.email
}

output "next_song_updater_service_account" {
  value = google_service_account.next_song_updater.email
}

output "nextjs_session_signing_key_secret" {
  value = google_secret_manager_secret.nextjs_session_signing_key.id
}

output "project_number" {
  value = data.google_project.current.number
}

output "vercel_wif_pool_id" {
  value = google_iam_workload_identity_pool.vercel.workload_identity_pool_id
}

output "vercel_wif_provider_id" {
  value = google_iam_workload_identity_pool_provider.vercel.workload_identity_pool_provider_id
}

output "vercel_oidc_subject" {
  value = local.vercel_oidc_subject
}
