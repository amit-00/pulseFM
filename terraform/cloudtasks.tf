resource "google_cloud_tasks_queue" "vote_queue" {
  name     = "vote-queue"
  location = var.region
}
