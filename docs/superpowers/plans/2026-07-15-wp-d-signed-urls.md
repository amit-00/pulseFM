# WP-D: Private Bucket + Signed URLs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pulsefm-generated-songs` stops being publicly readable; the Next.js server mints cached V4 signed URLs for tracks and the client consumes them.

**Architecture:** A `gcs-signer` server module builds a `Storage` client whose auth is an `Impersonated` client targeting the Next.js SA (source: the existing WIF external-account client in prod, ADC in dev), so `getSignedUrl` signs via IAM Credentials `signBlob` — no key files. A session-gated route `GET /api/track/[voteId]` serves `{url, expiresAt}` from a per-track server cache with stale-if-error. The client resolves audio URLs through that route and prefetches the next track's URL.

**Tech Stack:** Next.js 16 (route handlers), google-auth-library (`Impersonated`), `@google-cloud/storage` (**new client dependency — flagged and pre-approved for this WP; do not add anything else**), Terraform IAM.

**SEQUENCING:** This WP merges AFTER WP-A. Your branch may not contain WP-A's changes; the hook code referenced below (`applySnapshotTransitions`, `client/lib/pollDiff.ts`) comes from WP-A. If your base lacks it, implement against the current hook's equivalent call sites (`getAudioUrl` uses in `applySongChangeover`, `handlePlayPause`, and next-song prefetch) and note it — the orchestrator resolves the merge. Prefer rebasing onto the branch `wp-a-polling-state` if it exists in the repo.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-15-hardening-design.md` (WP-D section). If missing in your worktree, read `/Users/amit/Documents/repos/pulseFM/docs/superpowers/specs/2026-07-15-hardening-design.md`.
- No `terraform apply`, no deploys, no pushes. Verify: `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`.
- Client verification: `cd client && npm install && npx tsc --noEmit && npm run build`. There is no JS test runner in this repo — keep signing/cache logic in small pure-ish modules.
- Commit messages: conventional commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Terraform — private bucket, signing permissions

**Files:**
- Modify: `terraform/iam.tf`

- [ ] **Step 1:** Delete `google_storage_bucket_iam_member.generated_songs_public_encoded_reader` (the `allUsers` objectViewer binding, around line 282).

- [ ] **Step 2:** Add next to the other nextjs_server bindings:

```hcl
resource "google_storage_bucket_iam_member" "nextjs_server_songs_viewer" {
  bucket = google_storage_bucket.generated_songs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.nextjs_server.email}"
}

# signBlob for V4 URL signing (the existing OpenIdTokenCreator binding does not cover it)
resource "google_service_account_iam_member" "nextjs_server_sign_blobs" {
  service_account_id = google_service_account.nextjs_server.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.nextjs_server.email}"
}
```

- [ ] **Step 3:** Validate: `cd terraform && terraform init -backend=false && terraform validate && terraform fmt -check`.

- [ ] **Step 4: Commit** — `infra!: make songs bucket private; nextjs SA signs track URLs`

---

### Task 2: Server signer module + track route

**Files:**
- Modify: `client/package.json` (add `@google-cloud/storage` — run `npm install @google-cloud/storage` in `client/`)
- Create: `client/lib/server/gcs-signer.ts`
- Create: `client/app/api/track/[voteId]/route.ts`

**Interfaces:**
- Produces: `getSignedTrackUrl(voteId: string): Promise<{ url: string; expiresAt: number }>` — throws on first-ever signing failure for a track; returns last-known unexpired URL on subsequent failures.
- Route: `GET /api/track/<voteId>` → 200 `{url, expiresAt}` | 400 invalid voteId | 502 signing failed. Session auth comes from `client/proxy.ts`, which already gates `/api/*` (verify `/api/track` is not in its exclusion list; if the proxy uses an explicit route allowlist, add `/api/track` to it — read `client/proxy.ts` first and follow its pattern).

- [ ] **Step 1:** `cd client && npm install @google-cloud/storage` (this is the single approved new dependency).

- [ ] **Step 2: Create `client/lib/server/gcs-signer.ts`:**

```typescript
import { GoogleAuth, Impersonated } from "google-auth-library";
import { Storage } from "@google-cloud/storage";

const BUCKET = process.env.GCS_SONGS_BUCKET || "pulsefm-generated-songs";
const PREFIX = process.env.GCS_SONGS_PREFIX || "encoded/";
const URL_TTL_MS = 60 * 60 * 1000; // 1h signed URL lifetime
const REFRESH_MARGIN_MS = 10 * 60 * 1000; // re-sign when <10min left

const isLocalDev = process.env.NODE_ENV === "development";

type CachedUrl = { url: string; expiresAt: number };

let storage: Storage | null = null;
const urlCache = new Map<string, CachedUrl>();

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

async function getStorage(): Promise<Storage> {
  if (storage) return storage;

  const targetPrincipal = requireEnv("GCP_SERVICE_ACCOUNT_EMAIL");
  const scopes = ["https://www.googleapis.com/auth/devstorage.read_only"];

  let sourceClient;
  if (isLocalDev) {
    sourceClient = await new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/cloud-platform"],
    }).getClient();
  } else {
    // Reuse the WIF external-account client that cloud-run.ts already builds.
    const { getExternalAccountClientForSigning } = await import("@/lib/server/cloud-run");
    sourceClient = getExternalAccountClientForSigning();
  }

  const impersonated = new Impersonated({
    sourceClient,
    targetPrincipal,
    targetScopes: scopes,
    lifetime: 3600,
  });

  storage = new Storage({ projectId: requireEnv("GCP_PROJECT_ID"), authClient: impersonated });
  return storage;
}

async function signTrackUrl(voteId: string): Promise<CachedUrl> {
  const gcs = await getStorage();
  const expiresAt = Date.now() + URL_TTL_MS;
  const [url] = await gcs
    .bucket(BUCKET)
    .file(`${PREFIX}${voteId}.m4a`)
    .getSignedUrl({ version: "v4", action: "read", expires: expiresAt });
  return { url, expiresAt };
}

export async function getSignedTrackUrl(voteId: string): Promise<CachedUrl> {
  const cached = urlCache.get(voteId);
  const now = Date.now();
  if (cached && cached.expiresAt - now > REFRESH_MARGIN_MS) {
    return cached;
  }

  try {
    const fresh = await signTrackUrl(voteId);
    urlCache.set(voteId, fresh);
    return fresh;
  } catch (error) {
    if (cached && cached.expiresAt > now) {
      console.error("Track URL signing failed; serving last-known URL", { voteId, error });
      return cached;
    }
    throw error;
  }
}
```

- [ ] **Step 3: Export the WIF client from `client/lib/server/cloud-run.ts`.** Add (reusing the private `getExternalAccountClient`):

```typescript
export function getExternalAccountClientForSigning(): BaseExternalAccountClient {
  return getExternalAccountClient();
}
```

- [ ] **Step 4: Create `client/app/api/track/[voteId]/route.ts`:**

```typescript
import { NextResponse } from "next/server";
import { getSignedTrackUrl } from "@/lib/server/gcs-signer";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const VOTE_ID_PATTERN = /^[a-zA-Z0-9-]{1,64}$/; // uuid or "stubbed"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ voteId: string }> },
): Promise<Response> {
  const { voteId } = await params;
  if (!VOTE_ID_PATTERN.test(voteId)) {
    return NextResponse.json({ error: "Invalid voteId" }, { status: 400 });
  }
  try {
    const { url, expiresAt } = await getSignedTrackUrl(voteId);
    return NextResponse.json(
      { url, expiresAt },
      { headers: { "Cache-Control": "private, max-age=300" } },
    );
  } catch (error) {
    console.error("Failed to sign track URL", { voteId, error });
    return NextResponse.json({ error: "Track URL unavailable" }, { status: 502 });
  }
}
```

(Next.js 16 route handlers receive `params` as a Promise — if `npx tsc --noEmit` disagrees in this repo's Next version, match whatever `client/app/api/*/route.ts` neighbors do.)

- [ ] **Step 5: Check `client/proxy.ts`** — read it; confirm `/api/track` is covered by the auth enforcement (it gates `/api/*` except `/api/session` and `/api/auth/*`). If it applies per-route rate limits, add a limit entry for `/api/track` matching `/api/playback/state`'s tier.

- [ ] **Step 6: Verify**: `cd client && npx tsc --noEmit && npm run build` — success.

- [ ] **Step 7: Commit** — `feat(client): session-gated signed track URLs with server-side cache`

---

### Task 3: Client consumes signed URLs

**Files:**
- Create: `client/lib/audioUrl.ts`
- Modify: `client/hooks/useStreamPlayer.ts` (replace `getAudioUrl` uses)

**Interfaces:**
- Produces: `fetchAudioUrl(voteId: string): Promise<string>` — client-side cache keyed by voteId, honoring `expiresAt` with 5-minute refresh margin.

- [ ] **Step 1: Create `client/lib/audioUrl.ts`:**

```typescript
type CachedUrl = { url: string; expiresAt: number };

const cache = new Map<string, CachedUrl>();
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

export async function fetchAudioUrl(voteId: string): Promise<string> {
  const cached = cache.get(voteId);
  if (cached && cached.expiresAt - Date.now() > REFRESH_MARGIN_MS) {
    return cached.url;
  }
  const response = await fetch(`/api/track/${encodeURIComponent(voteId)}`, { cache: "no-store" });
  if (!response.ok) {
    if (cached && cached.expiresAt > Date.now()) return cached.url;
    throw new Error("Failed to resolve track URL");
  }
  const data = (await response.json()) as CachedUrl;
  cache.set(voteId, data);
  return data.url;
}
```

- [ ] **Step 2: Rewire `useStreamPlayer.ts`.** Delete the `getAudioUrl` function and replace every call site with the async fetch. With WP-A's hook in place there are three:

1. `applySongChangeover` — it is already async. Resolve both URLs up front:

```typescript
      const currentUrl = await fetchAudioUrl(currentVoteId);
      const nextUrl = nextVoteId ? await fetchAudioUrl(nextVoteId).catch(() => null) : null;
```

then use `currentUrl` where `getAudioUrl(currentVoteId)` was, and `if (nextVoteId && nextUrl) loadTrackToSlot(activeSlotValue, nextUrl);` (fall through to the existing `removeAttribute("src")` branch when `nextUrl` is null).

2. `handlePlayPause` — already async; same pattern (`await fetchAudioUrl(currentVoteId)`, and for the next-track preload `fetchAudioUrl(nextVoteId).then((url) => loadTrackToSlot(inactiveSlot, url)).catch(() => {})`).

3. The next-song prefetch in `applySnapshotTransitions` (WP-A) — replace:

```typescript
      } else if (transitions.nextSongChanged && next.nextSong.voteId) {
        void fetchAudioUrl(next.nextSong.voteId)
          .then((url) => loadTrackToSlot(getInactiveSlot(activeSlotRef.current), url))
          .catch(() => {});
      }
```

Import `fetchAudioUrl` from `@/lib/audioUrl`. Remove the now-unused `NEXT_PUBLIC_CDN_BASE_URL` / `NEXT_PUBLIC_BUCKET_BASE_URL` reads; grep: `grep -rn "NEXT_PUBLIC_CDN_BASE_URL\|NEXT_PUBLIC_BUCKET_BASE_URL\|getAudioUrl" client/` — no hits afterward.

- [ ] **Step 3: Verify**: `cd client && npx tsc --noEmit && npm run build` — success.

- [ ] **Step 4: Commit** — `feat(client)!: resolve audio via signed track URLs`

---

### Task 4: Full verification sweep

- [ ] `cd terraform && terraform validate && terraform fmt -check`; `cd client && npx tsc --noEmit && npm run build`.
- [ ] `grep -rn "allUsers" terraform/` — the ONLY remaining hit must be `cloud_run.tf` (playback-stream public invoker, intentionally kept).
- [ ] `git diff --stat` against your base — only WP-D files. Commit anything outstanding; report summary, including explicitly: the `@google-cloud/storage` dependency addition and anything you had to adapt because WP-A's hook wasn't in your base.
