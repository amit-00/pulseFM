import { NextResponse } from "next/server";

import { buildCloudCdnCookieValue } from "@/lib/server/cdn-cookie";
import { getSecretValue } from "@/lib/server/secrets";

const CDN_SIGNING_KEY_SECRET = process.env.CDN_SIGNING_KEY_SECRET || "";

const CDN_HOSTNAME = process.env.CDN_HOSTNAME || "";
const CDN_COOKIE_DOMAIN = process.env.CDN_COOKIE_DOMAIN || "";
const CDN_KEY_NAME = process.env.CDN_SIGNING_KEY_NAME || "";
const CDN_COOKIE_TTL_SEC = Number(process.env.CDN_COOKIE_TTL_SEC || "0");

export async function POST(request: Request) {
  const sessionId = request.headers.get("x-session-id");
  if (!sessionId) {
    return NextResponse.json({ error: "Missing session id" }, { status: 401 });
  }

  try {
    const keyValue = await getSecretValue(CDN_SIGNING_KEY_SECRET, "CDN_SIGNING_KEY_VALUE");
    const expiresEpochSec = Math.floor(Date.now() / 1000) + CDN_COOKIE_TTL_SEC;
    const cookieValue = buildCloudCdnCookieValue({
      urlPrefix: `https://${CDN_HOSTNAME}/encoded/`,
      keyName: CDN_KEY_NAME,
      keyValue,
      expiresEpochSec,
    });

    const response = NextResponse.json({ status: "ok", expiresAt: expiresEpochSec * 1000 });
    response.cookies.set({
      name: "Cloud-CDN-Cookie",
      value: cookieValue,
      httpOnly: true,
      secure: true,
      sameSite: "none",
      domain: CDN_COOKIE_DOMAIN,
      path: "/encoded/",
      expires: new Date(expiresEpochSec * 1000),
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Failed to mint CDN cookie" }, { status: 500 });
  }
}
