import { NextResponse } from "next/server";

function getPlaybackStreamBaseUrl(): string {
  const value = process.env.PLAYBACK_STREAM_URL;
  if (!value) {
    throw new Error("PLAYBACK_STREAM_URL is not set");
  }
  return value.replace(/\/$/, "");
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const url = `${getPlaybackStreamBaseUrl()}/stream`;
    const response = await fetch(url, {
      cache: "no-store",
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });

    if (!response.body) {
      return NextResponse.json({ error: "Playback stream unavailable" }, { status: 502 });
    }

    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    console.error("Failed to proxy playback stream", error);
    return NextResponse.json({ error: "Failed to open playback stream" }, { status: 500 });
  }
}
