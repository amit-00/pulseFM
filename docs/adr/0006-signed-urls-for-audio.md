# 0006. Signed URLs for Audio Delivery

Date: 2026-07-15
Status: Accepted

## Context

The `pulsefm-generated-songs` bucket granted `roles/storage.objectViewer` to
`allUsers` (pre-WP-D `terraform/iam.tf`), and the client composed public
`storage.googleapis.com` URLs from `NEXT_PUBLIC_BUCKET_BASE_URL` /
`NEXT_PUBLIC_CDN_BASE_URL`. Every generated track was world-readable to anyone who
guessed or shared a URL, independent of the session-gated API surface.

## Decision

Make the bucket private and gate audio behind session-scoped signed URLs (WP-D,
merged in `5ef8f32`):

- **Terraform** (`68ccf6f`): the `allUsers` binding is removed;
  `roles/storage.objectViewer` is granted to the Next.js server service account,
  which also gets `roles/iam.serviceAccountTokenCreator` on itself so it can call
  IAM Credentials `signBlob` (the existing `serviceAccountOpenIdTokenCreator`
  binding does not cover URL signing).
- **Server** (`client/app/api/track/[voteId]/route.ts`,
  `client/lib/server/gcs-signer.ts`): `GET /api/track/{voteId}` — session-gated
  like the rest of `/api/*` — mints a V4 signed URL for
  `encoded/{voteId}.m4a` via an `Impersonated` google-auth client layered over the
  same WIF external-account client used for Cloud Run OIDC (keyless; no SA key
  file). URLs are minted **per track, not per user**, live 1 hour, and are cached
  server-side with a 10-minute refresh margin; if re-signing fails, the last-known
  unexpired URL is served (stale-if-error).
- **Client** (`client/lib/audioUrl.ts`, `03ea15c`): stops composing bucket URLs,
  resolves audio through `/api/track/{voteId}` with its own cache (5-minute refresh
  margin, stale-if-error), and prefetches the next track's URL when the poll diff
  reports `nextSongChanged`. `NEXT_PUBLIC_BUCKET_BASE_URL` and
  `NEXT_PUBLIC_CDN_BASE_URL` are gone; the signer reads `GCS_SONGS_BUCKET` /
  `GCS_SONGS_PREFIX` (defaulting to `pulsefm-generated-songs` / `encoded/`).

## Consequences

- Track audio is no longer world-readable; access requires an authenticated session
  and expires with the URL.
- Audio delivery now depends on the WIF/IAM chain (Vercel OIDC → external-account
  client → `signBlob`). Mitigations: 1 h URL lifetime, server- and client-side
  caches, and stale-if-error on both layers mean a transient IAM outage degrades
  refresh, not playback.
- Unique query strings defeat shared HTTP caches, so GCS egress grows with listener
  count. This is the first decision to revisit if scale ever outweighs privacy
  (e.g. CDN with signed cookies/tokens).
- Dependency coupling (`15a37ec`): the client pins `google-auth-library` to `^9` —
  the same major `@google-cloud/storage@^7` depends on — so npm dedupes to one copy
  and Storage's internal `instanceof Impersonated` signing fast-path recognizes the
  injected auth client. If either package's major changes, re-verify with
  `npm ls google-auth-library` that it still dedupes; a split copy silently breaks
  `getSignedUrl`.
