import { cloudRunFetch } from "@/lib/server/cloud-run";

function getHeartbeatIngressBaseUrl(): string {
  return (
    process.env.HEARTBEAT_INGRESS_URL ||
    "https://heartbeat-ingress-156730433405.northamerica-northeast1.run.app"
  );
}

export async function heartbeatIngressFetch(sessionId: string): Promise<Response> {
  return cloudRunFetch({
    baseUrl: getHeartbeatIngressBaseUrl(),
    path: "/",
    method: "POST",
    headers: {
      "X-Session-Id": sessionId,
    },
  });
}
