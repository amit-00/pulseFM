import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";

import { getSecretValue } from "@/lib/server/secrets";
import { mintSignedSessionValue, SESSION_COOKIE_NAME } from "@/lib/server/session-cookie";

const SESSION_SIGNING_KEY_SECRET =
  process.env.SESSION_SIGNING_KEY_SECRET || "nextjs-session-signing-key";

export async function POST() {
  try {
    const signingKey = await getSecretValue(SESSION_SIGNING_KEY_SECRET, "SESSION_SIGNING_KEY");
    const sessionId = randomUUID();
    const signedValue = await mintSignedSessionValue(sessionId, signingKey);

    const response = NextResponse.json({ sessionId });
    response.cookies.set({
      name: SESSION_COOKIE_NAME,
      value: signedValue,
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
    });
    return response;
  } catch {
    return NextResponse.json({ error: "Failed to create session" }, { status: 500 });
  }
}
