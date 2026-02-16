import { NextResponse } from 'next/server';
import { heartbeatIngressFetch } from '@/lib/server/heartbeat-api';

export async function POST(request: Request) {
  const sessionId = request.headers.get('x-session-id');
  if (!sessionId) {
    return NextResponse.json({ error: 'Missing session id' }, { status: 401 });
  }
  try {
    const response = await heartbeatIngressFetch(sessionId);

    if (!response.ok) {
      return NextResponse.json(
        { error: "Heartbeat request failed" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: 'Failed to send heartbeat' },
      { status: 500 }
    );
  }
}
