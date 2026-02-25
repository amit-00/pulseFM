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

variable "encoder_image" {
  type        = string
  description = "Container image for encoder (tag or digest)"
}

variable "playback_service_image" {
  type        = string
  description = "Container image for playback-service (tag or digest)"
}

variable "playback_stream_image" {
  type        = string
  description = "Container image for playback-stream (tag or digest)"
}

variable "modal_dispatch_service_image" {
  type        = string
  description = "Container image for modal-dispatch-service (tag or digest)"
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

variable "nextjs_session_signing_key" {
  type        = string
  description = "HMAC secret used by Next.js for signed session cookies."
  sensitive   = true
}

variable "vercel_team_slug" {
  type        = string
  description = "Vercel team slug used for team issuer mode."
  default     = "amit00s-projects"
}

variable "vercel_project_slug" {
  type        = string
  description = "Vercel project slug allowed to impersonate the Next.js service account."
  default     = "pulse-fm"
}

variable "vercel_oidc_issuer_url" {
  type        = string
  description = "Vercel OIDC issuer URL."
  default     = "https://oidc.vercel.com/amit00s-projects"
}

variable "vercel_oidc_audience" {
  type        = string
  description = "Allowed audience for Vercel OIDC tokens."
  default     = "https://vercel.com/amit00s-projects"
}

variable "vercel_oidc_environment" {
  type        = string
  description = "Vercel environment allowed for OIDC impersonation."
  default     = "production"
}

variable "modal_token_id" {
  type        = string
  description = "Modal token ID."
  sensitive   = true
}

variable "modal_token_secret" {
  type        = string
  description = "Modal token secret."
  sensitive   = true
}
