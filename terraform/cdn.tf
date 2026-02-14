resource "google_compute_backend_bucket" "audio_cdn" {
  name        = "pulsefm-audio-cdn"
  bucket_name = google_storage_bucket.generated_songs.name
  enable_cdn  = true

  cdn_policy {
    signed_url_cache_max_age_sec = 900
  }
}

resource "google_compute_backend_bucket_signed_url_key" "audio_cdn" {
  name           = var.cdn_signed_cookie_key_name
  backend_bucket = google_compute_backend_bucket.audio_cdn.name
  key_value      = var.cdn_signed_cookie_key_value
}

resource "google_compute_url_map" "audio_cdn" {
  name            = "pulsefm-audio-cdn-map"
  default_service = google_compute_backend_bucket.audio_cdn.self_link
}

resource "google_compute_managed_ssl_certificate" "audio_cdn" {
  name = "pulsefm-audio-cdn-cert"
  managed {
    domains = [var.cdn_hostname]
  }
}

resource "google_compute_target_https_proxy" "audio_cdn" {
  name             = "pulsefm-audio-cdn-https-proxy"
  ssl_certificates = [google_compute_managed_ssl_certificate.audio_cdn.self_link]
  url_map          = google_compute_url_map.audio_cdn.self_link
}

resource "google_compute_global_address" "audio_cdn" {
  name = "pulsefm-audio-cdn-ip"
}

resource "google_compute_global_forwarding_rule" "audio_cdn_https" {
  name                  = "pulsefm-audio-cdn-https"
  target                = google_compute_target_https_proxy.audio_cdn.self_link
  ip_address            = google_compute_global_address.audio_cdn.address
  load_balancing_scheme = "EXTERNAL"
  port_range            = "443"
}

resource "google_dns_managed_zone" "audio_cdn" {
  name     = var.cdn_dns_zone_name
  dns_name = var.cdn_dns_name
}

resource "google_dns_record_set" "audio_cdn_a" {
  managed_zone = google_dns_managed_zone.audio_cdn.name
  name         = var.cdn_dns_name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.audio_cdn.address]
}
