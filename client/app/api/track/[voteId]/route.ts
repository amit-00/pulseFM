import { NextResponse } from "next/server";
import { getSignedTrackUrl } from "@/lib/server/gcs-signer";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const VOTE_ID_PATTERN = /^[a-zA-Z0-9-]{1,64}$/; // uuid or "stubbed"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ voteId: string }> },
): Promise<Response> {
  const { voteId } = await params;
  if (!VOTE_ID_PATTERN.test(voteId)) {
    return NextResponse.json({ error: "Invalid voteId" }, { status: 400 });
  }
  try {
    const { url, expiresAt } = await getSignedTrackUrl(voteId);
    return NextResponse.json(
      { url, expiresAt },
      { headers: { "Cache-Control": "private, max-age=300" } },
    );
  } catch (error) {
    console.error("Failed to sign track URL", { voteId, error });
    return NextResponse.json({ error: "Track URL unavailable" }, { status: 502 });
  }
}
