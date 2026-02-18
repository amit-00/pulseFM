export type PollTallies = Record<string, number>;

export interface SongState {
  voteId: string | null;
  startAt: number | null;
  endAt: number | null;
  durationMs: number | null;
}

export interface NextSongState {
  voteId: string | null;
  durationMs: number | null;
}

export interface PollState {
  voteId: string | null;
  options: string[];
  version: number | null;
  status?: "OPEN" | "CLOSED" | null;
  endAt?: number | null;
  winnerOption?: string | null;
  tallies: PollTallies;
}

export interface PlaybackStateSnapshot {
  currentSong: SongState;
  nextSong: NextSongState;
  poll: PollState;
  ts?: number;
}

export interface HelloEvent {
  voteId: string | null;
  ts: number;
  version: number | null;
  heartbeatSec: number;
}

export interface TallySnapshotEvent {
  voteId: string | null;
  ts: number;
  tallies: PollTallies;
  status?: "OPEN" | "CLOSED" | null;
  winnerOption?: string | null;
}

export interface TallyDeltaEvent {
  voteId: string | null;
  ts: number;
  delta: PollTallies;
}

export interface SongChangedEvent {
  voteId: string | null;
  ts: number;
  version: number | null;
}

export interface VoteClosedEvent {
  voteId: string | null;
  winnerOption?: string | null;
  ts: number;
}
