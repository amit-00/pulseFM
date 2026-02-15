import { NextResponse } from "next/server";

import { buildSignedUrl } from "@/lib/server/cdn-url";
import { getSecretValue } from "@/lib/server/secrets";

const CDN_SIGNING_KEY_SECRET = process.env.CDN_SIGNING_KEY_SECRET || "";
const CDN_HOSTNAME = process.env.CDN_HOSTNAME || "";
const CDN_KEY_NAME = process.env.CDN_SIGNING_KEY_NAME || "";
const CDN_URL_TTL_SEC = Number(process.env.CDN_URL_TTL_SEC || "900");

export async function POST(request: Request) {
  const sessionId = request.headers.get("x-session-id");
  if (!sessionId) {
    return NextResponse.json({ error: "Missing session id" }, { status: 401 });
  }

  let body: { voteIds?: string[] };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const voteIds = body.voteIds;
  if (!Array.isArray(voteIds) || voteIds.length === 0 || voteIds.length > 5) {
    return NextResponse.json({ error: "Provide 1-5 voteIds" }, { status: 400 });
  }

  try {
    const keyValue = await getSecretValue(CDN_SIGNING_KEY_SECRET, "CDN_SIGNING_KEY_VALUE");
    const expiresEpochSec = Math.floor(Date.now() / 1000) + CDN_URL_TTL_SEC;

    const urls: Record<string, string> = {};
    for (const voteId of voteIds) {
      const url = `https://${CDN_HOSTNAME}/encoded/${voteId}.m4a`;
      urls[voteId] = buildSignedUrl({ url, keyName: CDN_KEY_NAME, keyValue, expiresEpochSec });
    }

    return NextResponse.json({ urls, expiresAt: expiresEpochSec * 1000 });
  } catch (error) {
    console.error("[cdn-url] failed to sign URLs", {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return NextResponse.json({ error: "Failed to sign URLs" }, { status: 500 });
  }
}

