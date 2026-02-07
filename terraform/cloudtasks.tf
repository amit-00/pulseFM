resource "google_cloud_tasks_queue" "tally_queue" {
  name     = "tally-queue"
  location = var.region
}

resource "google_cloud_tasks_queue" "vote_orchestrator_queue" {
  name     = "vote-orchestrator-queue"
  location = var.region
}
