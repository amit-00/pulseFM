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

  // The repo pins google-auth-library to the same major @google-cloud/storage
  // depends on (v9) so npm dedupes to one copy and Storage's internal
  // `instanceof Impersonated` credential/signing fast-paths match this client.
  // If either package's major changes, re-verify with `npm ls google-auth-library`
  // that it still dedupes — a split copy silently breaks getSignedUrl.
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
