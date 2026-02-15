import { PlaybackStateSnapshot } from "@/lib/types";

export async function ensureSession(): Promise<void> {
  const sessionResponse = await fetch("/api/auth/session", { cache: "no-store" });
  if (!sessionResponse.ok) {
    throw new Error("Failed to verify session");
  }
  const session = (await sessionResponse.json()) as { user?: { name?: string } };
  if (session?.user?.name) {
    return;
  }

  const bootstrapResponse = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!bootstrapResponse.ok) {
    throw new Error("Failed to create session");
  }
}

export async function fetchPlaybackState(): Promise<PlaybackStateSnapshot> {
  const response = await fetch("/api/playback/state", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch playback state");
  }
  return response.json() as Promise<PlaybackStateSnapshot>;
}
