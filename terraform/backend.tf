terraform {
  backend "gcs" {
    bucket = "pulsefm-terraform-state"
    prefix = "pulsefm"
  }
}
