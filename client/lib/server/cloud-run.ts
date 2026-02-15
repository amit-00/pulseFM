import { getVercelOidcToken } from "@vercel/oidc";
import {
  BaseExternalAccountClient,
  ExternalAccountClient,
} from "google-auth-library";

type JsonValue = Record<string, unknown> | undefined;

type CloudRunFetchArgs = {
  baseUrl: string;
  path: string;
  method: "GET" | "POST";
  body?: JsonValue;
  headers?: HeadersInit;
};

let externalAccountClient: BaseExternalAccountClient | null = null;

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function buildWifAudience(): string {
  const projectNumber = requireEnv("GCP_PROJECT_NUMBER");
  const poolId = requireEnv("GCP_WORKLOAD_IDENTITY_POOL_ID");
  const providerId = requireEnv("GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID");
  return `//iam.googleapis.com/projects/${projectNumber}/locations/global/workloadIdentityPools/${poolId}/providers/${providerId}`;
}

function getExternalAccountClient(): BaseExternalAccountClient {
  if (externalAccountClient) {
    return externalAccountClient;
  }

  requireEnv("GCP_PROJECT_ID");
  const serviceAccountEmail = requireEnv("GCP_SERVICE_ACCOUNT_EMAIL");
  const audience = buildWifAudience();

  const client = ExternalAccountClient.fromJSON({
    type: "external_account",
    audience,
    scopes: ["https://www.googleapis.com/auth/cloud-platform"],
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    token_url: "https://sts.googleapis.com/v1/token",
    service_account_impersonation_url:
      `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${serviceAccountEmail}:generateAccessToken`,
    credential_source: { url: "http://localhost" },
    subject_token_supplier: {
      async getSubjectToken() {
        return getVercelOidcToken();
      },
    },
  }) as BaseExternalAccountClient;

  externalAccountClient = client;
  return externalAccountClient;
}

async function getAuthHeaders(targetAudience: string): Promise<Headers> {
  const serviceAccountEmail = requireEnv("GCP_SERVICE_ACCOUNT_EMAIL");
  const accessTokenResponse = await getExternalAccountClient().getAccessToken();
  const accessToken = accessTokenResponse.token;
  if (!accessToken) {
    throw new Error("Failed to obtain access token from Vercel OIDC federation");
  }

  const idTokenResponse = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${serviceAccountEmail}:generateIdToken`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        audience: targetAudience,
        includeEmail: true,
      }),
    },
  );
  if (!idTokenResponse.ok) {
    const detail = await idTokenResponse.text();
    throw new Error(`Failed to mint Cloud Run ID token: ${detail}`);
  }

  const idTokenPayload = (await idTokenResponse.json()) as { token?: string };
  if (!idTokenPayload.token) {
    throw new Error("IAM Credentials response did not contain an ID token");
  }

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${idTokenPayload.token}`);
  return headers;
}

export async function cloudRunFetch({
  baseUrl,
  path,
  method,
  body,
  headers,
}: CloudRunFetchArgs): Promise<Response> {
  const cleanBaseUrl = baseUrl.replace(/\/$/, "");
  const url = `${cleanBaseUrl}${path}`;
  const authHeaders = await getAuthHeaders(cleanBaseUrl);
  const mergedHeaders = new Headers(authHeaders);

  if (headers) {
    new Headers(headers).forEach((value, key) => {
      mergedHeaders.set(key, value);
    });
  }

  if (body) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  return fetch(url, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });
}
