# 0005. Modal Tokens via Secret Manager

Date: 2026-07-15
Status: Accepted

## Context

Before WP-C (`1750ab2`), `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` were plaintext
`env { value = var.modal_token_id }` entries on the modal-dispatch-service Cloud Run
template in `terraform/cloud_run.tf` — readable in the Cloud Console, in
`gcloud run services describe` output, and by anyone with viewer access to the
service. The repository already had the right pattern sitting next to it:
`nextjs_session_signing_key` in `terraform/secrets.tf` (Secret Manager secret +
version + scoped `secretAccessor` binding, consumed via `secret_key_ref`).

## Decision

Copy the existing pattern for both Modal tokens (`terraform/secrets.tf`):

- `google_secret_manager_secret` resources `modal-token-id` and
  `modal-token-secret`, with versions populated from the Terraform variables.
- A `roles/secretmanager.secretAccessor` binding scoped to each secret for the
  modal-dispatch-service service account only.
- The Cloud Run template consumes them via
  `env { value_source { secret_key_ref { ... version = "latest" } } }` instead of
  plaintext values (`terraform/cloud_run.tf`).

## Consequences

- Token values no longer appear in the Cloud Run service spec, console, or
  `describe` output; access requires the scoped `secretAccessor` grant, and Secret
  Manager gives versioning plus audit logging. Rotation is "add a new secret
  version" with no service redeploy (`version = "latest"`).
- **Residual risk, stated honestly:** the secret *versions* are still managed by
  Terraform, so the token values pass through — and persist in — Terraform state in
  the `pulsefm-terraform-state` GCS bucket. The real security boundary is access to
  that state bucket, not Secret Manager. Eliminating this would mean creating
  secret versions out-of-band (console/CLI) and leaving only the secret shells in
  Terraform; accepted as-is for now.
- One more set of Terraform variables (`modal_token_id`, `modal_token_secret`) must
  be supplied at apply time, same as the session signing key.
