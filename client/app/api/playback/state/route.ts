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
    const url = `${getPlaybackStreamBaseUrl()}/state`;
    const response = await fetch(url, { cache: "no-store" });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("Failed to proxy playback state", error);
    return NextResponse.json({ error: "Failed to fetch playback state" }, { status: 500 });
  }
}
