import { PlaybackStateSnapshot } from "@/lib/types";

type SessionRecord = {
  sessionId: string;
  token: string;
  lastVoteId?: string;
  lastVoteOption?: string;
};

const SESSION_STORAGE_KEY = "pulsefm.session";

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
}

function sessionEndpoint(path: string): string {
  return `${getApiBaseUrl()}${path}`;
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getStoredSession(): SessionRecord | null {
  if (!canUseStorage()) {
    return null;
  }
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as SessionRecord;
  } catch {
    return null;
  }
}

function setStoredSession(session: SessionRecord): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

export async function ensureSession(): Promise<SessionRecord> {
  const existing = getStoredSession();
  if (existing?.sessionId && existing.token) {
    return existing;
  }

  const bootstrapResponse = await fetch(sessionEndpoint("/api/session/bootstrap"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!bootstrapResponse.ok) {
    throw new Error("Failed to create session");
  }

  const session = (await bootstrapResponse.json()) as SessionRecord;
  setStoredSession(session);
  return session;
}

async function authHeaders(): Promise<HeadersInit> {
  const session = await ensureSession();
  return {
    Authorization: `Bearer ${session.token}`,
  };
}

export async function fetchPlaybackState(): Promise<PlaybackStateSnapshot> {
  const response = await fetch(sessionEndpoint("/api/state"), {
    cache: "no-store",
    headers: await authHeaders(),
  });
  if (!response.ok) {
    throw new Error("Failed to fetch playback state");
  }
  return response.json() as Promise<PlaybackStateSnapshot>;
}

export async function submitVote(voteId: string, option: string): Promise<void> {
  const response = await fetch(sessionEndpoint("/api/vote"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },
    body: JSON.stringify({ voteId, option }),
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(error.error || "Vote failed");
  }

  const current = getStoredSession();
  if (current) {
    setStoredSession({
      ...current,
      lastVoteId: voteId,
      lastVoteOption: option,
    });
  }
}

export function fetchVoteStatus(
  voteId: string | null,
): { hasVoted: boolean; selectedOption: string | null } {
  if (!voteId) {
    return { hasVoted: false, selectedOption: null };
  }
  const session = getStoredSession();
  if (session?.lastVoteId === voteId && session.lastVoteOption) {
    return { hasVoted: true, selectedOption: session.lastVoteOption };
  }
  return { hasVoted: false, selectedOption: null };
}
