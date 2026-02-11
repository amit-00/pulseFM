resource "google_compute_network" "memorystore" {
  name                    = "pulsefm-memorystore"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "memorystore" {
  name          = "pulsefm-memorystore"
  region        = var.region
  network       = google_compute_network.memorystore.id
  ip_cidr_range = var.memorystore_subnet_cidr
}

resource "google_vpc_access_connector" "memorystore" {
  name          = "pulsefm-memorystore"
  region        = var.region
  network       = google_compute_network.memorystore.name
  ip_cidr_range = var.memorystore_connector_cidr
}

resource "google_redis_instance" "memorystore" {
  name               = "pulsefm-memorystore"
  region             = var.region
  tier               = "BASIC"
  memory_size_gb     = var.memorystore_size_gb
  redis_version      = "REDIS_7_0"
  authorized_network = google_compute_network.memorystore.id

  depends_on = [google_project_service.services, google_compute_subnetwork.memorystore]
}
