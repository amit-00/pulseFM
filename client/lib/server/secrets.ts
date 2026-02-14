import { SecretManagerServiceClient } from "@google-cloud/secret-manager";

const client = new SecretManagerServiceClient();
const cache = new Map<string, string>();

function _resolveSecretVersionPath(secretRef: string): string {
  if (secretRef.includes("/versions/")) {
    return secretRef;
  }
  if (secretRef.startsWith("projects/")) {
    return `${secretRef}/versions/latest`;
  }
  const projectId =
    process.env.GOOGLE_CLOUD_PROJECT ||
    process.env.GCLOUD_PROJECT ||
    process.env.GCP_PROJECT ||
    process.env.PROJECT_ID;
  if (!projectId) {
    throw new Error("Missing project id for Secret Manager access");
  }
  return `projects/${projectId}/secrets/${secretRef}/versions/latest`;
}

export async function getSecretValue(secretRef: string, envFallback?: string): Promise<string> {
  if (envFallback) {
    const value = process.env[envFallback];
    if (value) {
      return value;
    }
  }

  const versionPath = _resolveSecretVersionPath(secretRef);
  const cached = cache.get(versionPath);
  if (cached) {
    return cached;
  }

  const [version] = await client.accessSecretVersion({ name: versionPath });
  const value = version.payload?.data?.toString("utf8");
  if (!value) {
    throw new Error(`Secret version has no payload: ${versionPath}`);
  }
  cache.set(versionPath, value);
  return value;
}
