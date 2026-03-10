import { cloudRunFetch } from "@/lib/server/cloud-run";

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
  return cloudRunFetch({
    baseUrl: _getVoteApiBaseUrl(),
    path,
    method,
    body,
    headers: {
      "X-Session-Id": sessionId,
    },
  });
}
