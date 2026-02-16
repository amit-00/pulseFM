import { NextResponse } from 'next/server';
import { voteApiFetch } from '@/lib/server/vote-api';

export async function POST(request: Request) {
  const body = await request.json();
  const { option } = body;
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
    return NextResponse.json(data);
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