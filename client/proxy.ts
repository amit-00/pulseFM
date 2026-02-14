import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME, verifySignedSessionValue } from "@/lib/server/session-cookie";

const EXEMPT_PATHS = new Set(["/api/session"]);

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!pathname.startsWith("/api/") || EXEMPT_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  const signingKey = process.env.SESSION_SIGNING_KEY;
  if (!signingKey) {
    return NextResponse.json({ error: "Server misconfigured" }, { status: 500 });
  }

  const cookieValue = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  const sessionId = await verifySignedSessionValue(cookieValue, signingKey);
  if (!sessionId) {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("X-Session-Id", sessionId);
  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: ["/api/:path*"],
};
