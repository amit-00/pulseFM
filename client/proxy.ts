import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { Redis } from "@upstash/redis";

const EXEMPT_PATHS = new Set(["/api/session"]);
const redis = Redis.fromEnv();

type RateRule = {
  key: string;
  limit: number;
  windowSec: number;
};

const RATE_RULES: Array<{ path: string; rules: RateRule[] }> = [
  {
    path: "/api/vote",
    rules: [
      { key: "vote:min", limit: 10, windowSec: 60 },
      { key: "vote:hour", limit: 60, windowSec: 3600 },
    ],
  },
  {
    path: "/api/heartbeat",
    rules: [{ key: "heartbeat:min", limit: 6, windowSec: 60 }],
  },
  {
    path: "/api/cdn-url",
    rules: [
      { key: "cdn-url:min", limit: 3, windowSec: 60 },
      { key: "cdn-url:hour", limit: 10, windowSec: 3600 },
    ],
  },
];

function getRulesForPath(pathname: string): RateRule[] {
  const match = RATE_RULES.find((route) => pathname === route.path);
  return match ? match.rules : [];
}

function getWindowContext(windowSec: number): { bucket: number; retryAfterSec: number } {
  const nowSec = Math.floor(Date.now() / 1000);
  const bucket = Math.floor(nowSec / windowSec);
  const retryAfterSec = Math.max(1, windowSec - (nowSec % windowSec));
  return { bucket, retryAfterSec };
}

async function enforceRateLimits(sessionId: string, pathname: string): Promise<number | null> {
  const rules = getRulesForPath(pathname);
  if (rules.length === 0) {
    return null;
  }

  let maxRetryAfterSec = 0;
  for (const rule of rules) {
    const { bucket, retryAfterSec } = getWindowContext(rule.windowSec);
    const key = `pulsefm:rl:${rule.key}:sid:${sessionId}:b:${bucket}`;
    const count = await redis.incr(key);
    if (count === 1) {
      await redis.expire(key, rule.windowSec + 5);
    }
    if (count > rule.limit) {
      maxRetryAfterSec = Math.max(maxRetryAfterSec, retryAfterSec);
    }
  }

  return maxRetryAfterSec > 0 ? maxRetryAfterSec : null;
}

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

  try {
    const retryAfterSec = await enforceRateLimits(sessionId, pathname);
    if (retryAfterSec !== null) {
      const response = NextResponse.json(
        { error: "rate_limited", retryAfterSec },
        { status: 429 },
      );
      response.headers.set("Retry-After", String(retryAfterSec));
      return response;
    }
  } catch (error) {
    console.error("Rate limiter unavailable", error);
    return NextResponse.json({ error: "Rate limiter unavailable" }, { status: 500 });
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
