import type { Descriptor } from "./options";

export type PollStatus = "OPEN" | "CLOSED";

export type SongState = {
  voteId: string | null;
  startAt: number | null;
  endAt: number | null;
  durationMs: number | null;
  audioUrl?: string | null;
};

export type NextSongState = {
  voteId: string | null;
  durationMs: number | null;
  audioUrl?: string | null;
};

export type PollState = {
  voteId: string | null;
  options: string[];
  tallies: Record<string, number>;
  version: number;
  status: PollStatus;
  endAt: number | null;
  winnerOption: string | null;
};

export type PlaybackSnapshot = {
  currentSong: SongState;
  nextSong: NextSongState;
  poll: PollState;
  listeners: number;
  ts: number;
};

export type ReadySong = {
  voteId: string;
  durationMs: number;
  audioUrl: string;
  winnerOption: string | null;
  createdAt: number;
};

export type StationState = {
  stationId: string;
  version: number;
  currentSong: SongState;
  nextSong: NextSongState;
  poll: PollState;
  readySongs: ReadySong[];
  scheduledEvents: ScheduledEvent[];
  activeSessions: Record<string, number>;
};

export type ScheduledEvent = {
  type: "vote_close" | "song_end";
  dueAt: number;
  voteId?: string;
};

export type CastVoteInput = {
  sessionId: string;
  voteId: string;
  option: string;
};

export type SeedPayload = {
  currentSong?: SongState;
  nextSong?: NextSongState;
  poll?: Partial<PollState>;
};

export type BootstrapSession = {
  sessionId: string;
  token: string;
};

export type GenerationWorkflowParams = {
  voteId: string;
  winnerOption: string;
  descriptor: Descriptor;
};

export type GenerationReadyPayload = {
  voteId: string;
  workflowInstanceId: string;
  externalJobId?: string;
  durationMs: number;
  r2Key: string;
  publicUrl: string;
  winnerOption?: string | null;
};

export interface Env {
  DB: D1Database;
  AUDIO_BUCKET: R2Bucket;
  STATION_CONTROL: DurableObjectNamespace;
  GENERATE_SONG_WORKFLOW: Workflow;
  APP_ORIGIN: string;
  PUBLIC_AUDIO_BASE_URL: string;
  PUBLIC_API_BASE_URL: string;
  EXTERNAL_GENERATOR_URL: string;
  SESSION_TOKEN_SECRET: string;
  INTERNAL_CALLBACK_SECRET: string;
  DESCRIPTOR_WINDOW_SIZE: string;
  POLL_WINDOW_SEC: string;
  PRESENCE_TTL_SEC: string;
  GENERATION_TIMEOUT_SEC: string;
}
