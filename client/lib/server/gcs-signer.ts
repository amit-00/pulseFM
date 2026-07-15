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

type SignerAuthBridge = {
  getCredentials: () => Promise<{ client_email: string }>;
  sign: (data: string) => Promise<string>;
};

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

  const gcs = new Storage({ projectId: requireEnv("GCP_PROJECT_ID") });

  // Version-skew bridge: @google-cloud/storage@7 bundles google-auth-library@9
  // while this repo uses v10, so passing the v10 Impersonated client as
  // `authClient` fails at runtime — storage's internal v9 GoogleAuth wrapper
  // resolves credentials through `instanceof Impersonated` fast-paths that a
  // v10 instance never matches, and URL signing falls through to ADC discovery.
  // Replicate those exact fast-paths (v9 googleauth.js: getCredentialsAsync and
  // sign) so getSignedUrl signs via the impersonated IAM Credentials signBlob.
  const authBridge = gcs.authClient as unknown as SignerAuthBridge;
  authBridge.getCredentials = async () => ({ client_email: targetPrincipal });
  authBridge.sign = async (data: string) => {
    const { signedBlob } = await impersonated.sign(data);
    return signedBlob;
  };

  storage = gcs;
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
