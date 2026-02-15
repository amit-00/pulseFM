import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

const EXEMPT_PATHS = new Set(["/api/session"]);

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    !pathname.startsWith("/api/") ||
    EXEMPT_PATHS.has(pathname) ||
    pathname.startsWith("/api/auth/")
  ) {
    return NextResponse.next();
  }

  const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "Server misconfigured" }, { status: 500 });
  }

  const token = await getToken({ req: request, secret });
  const sessionId = typeof token?.sub === "string" ? token.sub : null;
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
