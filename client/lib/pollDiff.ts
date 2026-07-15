import { PlaybackStateSnapshot } from "@/lib/types";

export const POLL_INTERVAL_MS = 2000;
export const POLL_JITTER_MS = 500;
export const BOUNDARY_GRACE_MS = 300;

export type SnapshotTransitions = {
  songChanged: boolean;
  nextSongChanged: boolean;
  voteClosed: boolean;
  pollChanged: boolean;
};

export function diffSnapshots(
  prev: PlaybackStateSnapshot | null,
  next: PlaybackStateSnapshot,
): SnapshotTransitions {
  if (!prev) {
    return { songChanged: false, nextSongChanged: false, voteClosed: false, pollChanged: false };
  }
  return {
    songChanged: prev.currentSong.voteId !== next.currentSong.voteId,
    nextSongChanged:
      prev.nextSong.voteId !== next.nextSong.voteId ||
      prev.nextSong.durationMs !== next.nextSong.durationMs,
    voteClosed: prev.poll.status === "OPEN" && next.poll.status === "CLOSED",
    pollChanged: prev.poll.voteId !== next.poll.voteId,
  };
}

export function nextPollDelayMs(snapshot: PlaybackStateSnapshot | null, now: number): number {
  const jitter = Math.floor(Math.random() * POLL_JITTER_MS);
  const base = POLL_INTERVAL_MS + jitter;
  const songEndAt = snapshot?.currentSong?.endAt ?? null;
  if (songEndAt && songEndAt > now) {
    // Wake just after the changeover boundary if it lands before the next regular poll.
    const untilBoundary = songEndAt - now + BOUNDARY_GRACE_MS;
    if (untilBoundary < base) return Math.max(250, untilBoundary);
  }
  return base;
}
