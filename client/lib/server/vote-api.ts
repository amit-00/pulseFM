import { GoogleAuth } from "google-auth-library";

const auth = new GoogleAuth();

function _getVoteApiBaseUrl(): string {
  return (
    process.env.VOTE_API_URL ||
    "https://vote-api-156730433405.northamerica-northeast1.run.app"
  );
}

type JsonValue = Record<string, unknown> | undefined;

export async function voteApiFetch(
  path: string,
  method: "GET" | "POST",
  sessionId: string,
  body?: JsonValue,
): Promise<Response> {
  const baseUrl = _getVoteApiBaseUrl().replace(/\/$/, "");
  const url = `${baseUrl}${path}`;
  const idTokenClient = await auth.getIdTokenClient(baseUrl);
  const authHeaders = await idTokenClient.getRequestHeaders(url);
  const headers = new Headers({
    ...authHeaders,
    "X-Session-Id": sessionId,
  });
  if (body) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
}
