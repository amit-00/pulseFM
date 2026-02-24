resource "google_cloud_tasks_queue" "tally_queue" {
  name     = "tally-queue"
  location = var.region
}

resource "google_cloud_tasks_queue" "playback_queue" {
  name     = "playback-queue"
  location = var.region
}

resource "google_cloud_tasks_queue" "modal_dispatch_queue" {
  name     = "modal-dispatch-queue"
  location = var.region
}
