import { NextResponse } from 'next/server';
import { getToken, encode } from 'next-auth/jwt';
import { voteApiFetch } from '@/lib/server/vote-api';

const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET || "";
const secureCookie = process.env.NODE_ENV === "production";
const cookieName = secureCookie
  ? "__Secure-authjs.session-token"
  : "authjs.session-token";

export async function POST(request: Request) {
  const body = await request.json();
  const { voteId, option } = body;
  if (!option) {
    return NextResponse.json({ error: 'Option is required' }, { status: 400 });
  }
  const sessionId = request.headers.get('x-session-id');
  if (!sessionId) {
    return NextResponse.json({ error: 'Missing session id' }, { status: 401 });
  }
  try {
    const response = await voteApiFetch('/vote', 'POST', sessionId, body);

    if (!response.ok) {
      return NextResponse.json(
        { error: "Vote request failed" },
        { status: response.status }
      );
    }

    const data = await response.json();

    // Stamp the vote into the session JWT so other tabs can read it
    const res = NextResponse.json(data);
    try {
      const token = await getToken({ req: request, secret });
      if (token && typeof voteId === "string" && typeof option === "string") {
        token.lastVoteId = voteId;
        token.lastVoteOption = option;
        const newJwt = await encode({ token, secret, salt: cookieName });
        res.cookies.set(cookieName, newJwt, {
          httpOnly: true,
          secure: secureCookie,
          sameSite: "lax",
          path: "/",
        });
      }
    } catch (cookieErr) {
      // Non-fatal: the vote succeeded even if the cookie update fails
      console.error("Failed to update session cookie with vote", cookieErr);
    }

    return res;
  } catch (error) {
    console.error("Failed to send vote request", {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    });
    return NextResponse.json(
      { error: "Failed to send vote request" },
      { status: 500 }
    );
  }
}
