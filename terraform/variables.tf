variable "project_id" {
  type    = string
  default = "pulsefm-484500"
}

variable "region" {
  type    = string
  default = "northamerica-northeast1"
}

variable "artifact_repo" {
  type    = string
  default = "pulsefm"
}

variable "vote_api_image" {
  type        = string
  description = "Container image for vote-api (tag or digest)"
}

variable "vote_orchestrator_image" {
  type        = string
  description = "Container image for vote-orchestrator (tag or digest)"
}

variable "encoder_image" {
  type        = string
  description = "Container image for encoder (tag or digest)"
}

variable "playback_orchestrator_image" {
  type        = string
  description = "Container image for playback-orchestrator (tag or digest)"
}

variable "vote_stream_image" {
  type        = string
  description = "Container image for vote-stream (tag or digest)"
}

variable "session_jwt_secret" {
  type        = string
  description = "HMAC secret for session JWTs"
  sensitive   = true
}

variable "window_seconds" {
  type    = number
  default = 300
}

variable "options_per_window" {
  type    = number
  default = 4
}

variable "memorystore_size_gb" {
  type    = number
  default = 1
}

variable "memorystore_subnet_cidr" {
  type    = string
  default = "10.10.0.0/24"
}

variable "memorystore_connector_cidr" {
  type    = string
  default = "10.8.0.0/28"
}

variable "github_owner" {
  type        = string
  description = "GitHub org/user for Cloud Build trigger"
}

variable "github_repo" {
  type        = string
  description = "GitHub repo name for Cloud Build trigger"
}

variable "github_branch" {
  type    = string
  default = "main"
}
