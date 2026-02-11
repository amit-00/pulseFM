import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

export async function POST() {
  try {
    const cookieStore = await cookies();
    const allCookies = cookieStore.getAll();
    const cookieHeader = allCookies
      .map(c => `${c.name}=${c.value}`)
      .join('; ');

    const response = await fetch(
      'https://vote-api-156730433405.northamerica-northeast1.run.app/heartbeat',
      {
        method: 'POST',
        headers: {
          ...(cookieHeader && { Cookie: cookieHeader }),
        },
      }
    );

    if (!response.ok) {
      const status = response.status;
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: response.statusText || 'Heartbeat failed' };
      }
      return NextResponse.json(errorData, { status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to send heartbeat' },
      { status: 500 }
    );
  }
}
