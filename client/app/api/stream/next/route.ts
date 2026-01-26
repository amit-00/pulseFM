import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const response = await fetch(
      'http://localhost:8080/api/stream/next'
    );

    // Handle 4XX and 5XX errors
    if (!response.ok) {
      const status = response.status;
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: response.statusText || 'Request failed' };
      }
      return NextResponse.json(errorData, { status });
    }

    const { request_id, signed_url } = await response.json();

    return NextResponse.json({ request_id, signed_url });

  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch' }, { status: 500 });
  }
}