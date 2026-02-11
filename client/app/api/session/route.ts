import { NextResponse } from 'next/server';

export async function POST() {
  try {
    const response = await fetch(
      'https://vote-api-156730433405.northamerica-northeast1.run.app/session',
      { method: 'POST' }
    );

    if (!response.ok) {
      const status = response.status;
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: response.statusText || 'Session creation failed' };
      }
      return NextResponse.json(errorData, { status });
    }

    const data = await response.json(); // { sessionId, expiresAt }

    // Build the client response with the JSON payload
    const clientResponse = NextResponse.json(data);

    // Forward all Set-Cookie headers from the upstream response
    const setCookieHeaders = response.headers.getSetCookie();
    for (const cookie of setCookieHeaders) {
      clientResponse.headers.append('Set-Cookie', cookie);
    }

    return clientResponse;
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to create session' },
      { status: 500 }
    );
  }
}