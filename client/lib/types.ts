export type PollTallies = Record<string, number>;

export interface SongState {
  voteId: string | null;
  startAt: number | null;
  endAt: number | null;
  durationMs: number | null;
  audioUrl?: string | null;
}

export interface NextSongState {
  voteId: string | null;
  durationMs: number | null;
  audioUrl?: string | null;
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
  listeners?: number | null;
  ts?: number;
  redisAvailable?: boolean;
}
