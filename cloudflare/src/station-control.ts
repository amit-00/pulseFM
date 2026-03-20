import { DurableObject } from "cloudflare:workers";
import { DESCRIPTORS, sampleOptions } from "./options";
import { listReadySongs, snapshotToPollRows, upsertPollRound } from "./db";
import type {
  CastVoteInput,
  Env,
  GenerationWorkflowParams,
  PlaybackSnapshot,
  PollState,
  ReadySong,
  ScheduledEvent,
  SeedPayload,
  SongState,
  StationState,
} from "./types";

const STATE_KEY = "station-state";
const VOTE_CLOSE_LEAD_MS = 60_000;

function nowMs(): number {
  return Date.now();
}

function toIso(ts: number): string {
  return new Date(ts).toISOString();
}

function parseNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function getWinner(tallies: Record<string, number>): string | null {
  const entries = Object.entries(tallies);
  if (entries.length === 0) {
    return null;
  }
  const max = Math.max(...entries.map(([, count]) => count));
  const tied = entries.filter(([, count]) => count === max).map(([option]) => option);
  if (tied.length === 0) {
    return null;
  }
  const index = Math.floor(Math.random() * tied.length);
  return tied[index] ?? null;
}

function cloneScheduledEvents(events: ScheduledEvent[]): ScheduledEvent[] {
  return [...events].sort((a, b) => a.dueAt - b.dueAt);
}

export class StationControl extends DurableObject<Env> {
  private stateCache?: StationState;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
  }

  private get pollWindowMs(): number {
    return parseNumber(this.env.POLL_WINDOW_SEC, 300) * 1000;
  }

  private get descriptorWindowSize(): number {
    return parseNumber(this.env.DESCRIPTOR_WINDOW_SIZE, 4);
  }

  private get presenceTtlMs(): number {
    return parseNumber(this.env.PRESENCE_TTL_SEC, 30) * 1000;
  }

  private defaultSongState(): SongState {
    return {
      voteId: null,
      startAt: null,
      endAt: null,
      durationMs: null,
      audioUrl: null,
    };
  }

  private defaultPoll(version = 1): PollState {
    const voteId = crypto.randomUUID();
    const options = sampleOptions(this.descriptorWindowSize);
    return {
      voteId,
      options,
      tallies: Object.fromEntries(options.map((option) => [option, 0])),
      version,
      status: "OPEN",
      endAt: nowMs() + this.pollWindowMs,
      winnerOption: null,
    };
  }

  private async ensureState(): Promise<StationState> {
    if (this.stateCache) {
      return this.stateCache;
    }

    const existing = await this.ctx.storage.get<StationState>(STATE_KEY);
    if (existing) {
      this.stateCache = this.cleanupState(existing);
      return this.stateCache;
    }

    const readySongs = await listReadySongs(this.env.DB);
    const firstReady = readySongs.shift() ?? null;
    const currentSong = firstReady ? this.readySongToCurrentSong(firstReady) : this.defaultSongState();
    const nextSeed = readySongs.shift() ?? null;
    const nextSong = nextSeed
      ? { voteId: nextSeed.voteId, durationMs: nextSeed.durationMs, audioUrl: nextSeed.audioUrl }
      : { voteId: null, durationMs: null, audioUrl: null };
    const initialPoll = this.defaultPoll(1);

    const initial: StationState = {
      stationId: "main",
      version: 1,
      currentSong,
      nextSong,
      poll: initialPoll,
      readySongs,
      scheduledEvents: [],
      activeSessions: {},
    };

    await this.onPollOpened(initial);
    await this.scheduleFromState(initial);
    await this.saveState(initial);
    this.stateCache = initial;
    return initial;
  }

  private cleanupState(state: StationState): StationState {
    const cutoff = nowMs();
    const activeSessions = Object.fromEntries(
      Object.entries(state.activeSessions).filter(([, expiresAt]) => expiresAt > cutoff),
    );
    return {
      ...state,
      activeSessions,
      scheduledEvents: cloneScheduledEvents(
        state.scheduledEvents.filter((event) => event.dueAt > cutoff - 1000),
      ),
    };
  }

  private readySongToCurrentSong(song: ReadySong): SongState {
    const startAt = nowMs();
    return {
      voteId: song.voteId,
      startAt,
      endAt: startAt + song.durationMs,
      durationMs: song.durationMs,
      audioUrl: song.audioUrl,
    };
  }

  private buildSnapshot(state: StationState): PlaybackSnapshot {
    const cleaned = this.cleanupState(state);
    return {
      currentSong: cleaned.currentSong,
      nextSong: cleaned.nextSong,
      poll: cleaned.poll,
      listeners: Object.keys(cleaned.activeSessions).length,
      ts: nowMs(),
    };
  }

  private async saveState(state: StationState): Promise<void> {
    this.stateCache = state;
    await this.ctx.storage.put(STATE_KEY, state);
  }

  private async scheduleFromState(state: StationState): Promise<void> {
    const events: ScheduledEvent[] = [];
    if (state.poll.status === "OPEN" && state.poll.voteId && state.poll.endAt) {
      events.push({
        type: "vote_close",
        dueAt: state.poll.endAt,
        voteId: state.poll.voteId,
      });
    }
    if (state.currentSong.voteId && state.currentSong.endAt) {
      events.push({
        type: "song_end",
        dueAt: state.currentSong.endAt,
        voteId: state.currentSong.voteId,
      });
    }
    state.scheduledEvents = cloneScheduledEvents(events);
    const nextDueAt = state.scheduledEvents[0]?.dueAt;
    if (nextDueAt) {
      await this.ctx.storage.setAlarm(nextDueAt);
      return;
    }
    await this.ctx.storage.deleteAlarm();
  }

  private async onPollOpened(state: StationState): Promise<void> {
    if (!state.poll.voteId) {
      return;
    }
    const openedAt = state.currentSong.startAt ? toIso(state.currentSong.startAt) : toIso(nowMs());
    await upsertPollRound(this.env.DB, {
      voteId: state.poll.voteId,
      stationId: state.stationId,
      openedAt,
      status: "OPEN",
      version: state.version,
    });
  }

  private async openNextPoll(state: StationState): Promise<void> {
    const version = state.version + 1;
    state.version = version;
    state.poll = this.defaultPoll(version);

    if (state.currentSong.endAt) {
      const desiredEndAt = state.currentSong.endAt - VOTE_CLOSE_LEAD_MS;
      state.poll.endAt = desiredEndAt > nowMs() ? desiredEndAt : nowMs() + 15_000;
    }

    await this.onPollOpened(state);
  }

  private async closePoll(state: StationState): Promise<void> {
    if (state.poll.status !== "OPEN" || !state.poll.voteId) {
      return;
    }

    state.poll.status = "CLOSED";
    state.poll.winnerOption = getWinner(state.poll.tallies);
    state.poll.endAt = nowMs();

    await snapshotToPollRows(this.env.DB, this.buildSnapshot(state));

    if (state.poll.winnerOption) {
      const descriptor = DESCRIPTORS[state.poll.winnerOption];
      if (descriptor) {
        const params: GenerationWorkflowParams = {
          voteId: state.poll.voteId,
          winnerOption: state.poll.winnerOption,
          descriptor,
        };
        await this.env.GENERATE_SONG_WORKFLOW.create({
          id: state.poll.voteId,
          params,
        });
      }
    }
  }

  private promoteReadySong(state: StationState): void {
    const promoted = state.nextSong.voteId
      ? {
          voteId: state.nextSong.voteId,
          durationMs: state.nextSong.durationMs,
          audioUrl: state.nextSong.audioUrl ?? null,
        }
      : state.readySongs.shift() ?? null;

    if (!promoted) {
      state.currentSong = this.defaultSongState();
      state.nextSong = { voteId: null, durationMs: null, audioUrl: null };
      return;
    }

    const startAt = nowMs();
    state.currentSong = {
      voteId: promoted.voteId,
      startAt,
      endAt: startAt + (promoted.durationMs ?? 0),
      durationMs: promoted.durationMs,
      audioUrl: promoted.audioUrl ?? null,
    };

    const next = state.readySongs.shift() ?? null;
    state.nextSong = next
      ? { voteId: next.voteId, durationMs: next.durationMs, audioUrl: next.audioUrl }
      : { voteId: null, durationMs: null, audioUrl: null };
  }

  private async rotateSong(state: StationState): Promise<void> {
    this.promoteReadySong(state);
    if (state.currentSong.voteId) {
      await this.openNextPoll(state);
      return;
    }
    state.poll = {
      ...state.poll,
      status: "CLOSED",
      endAt: nowMs(),
    };
  }

  async getPublicSnapshot(sessionId?: string): Promise<PlaybackSnapshot> {
    const state = await this.ensureState();
    if (sessionId) {
      state.activeSessions[sessionId] = nowMs() + this.presenceTtlMs;
      await this.saveState(state);
    }
    return this.buildSnapshot(state);
  }

  async castVote(input: CastVoteInput): Promise<PlaybackSnapshot> {
    const state = await this.ensureState();
    if (state.poll.status !== "OPEN") {
      throw new Error("Vote closed");
    }
    if (state.poll.voteId !== input.voteId) {
      throw new Error("Invalid voteId");
    }
    if (!state.poll.options.includes(input.option)) {
      throw new Error("Invalid option");
    }

    const voteKey = `vote:${state.poll.voteId}:${input.sessionId}`;
    const alreadyVoted = await this.ctx.storage.get<boolean>(voteKey);
    if (alreadyVoted) {
      throw new Error("Duplicate vote");
    }

    state.poll.tallies[input.option] = (state.poll.tallies[input.option] ?? 0) + 1;
    state.activeSessions[input.sessionId] = nowMs() + this.presenceTtlMs;

    await this.ctx.storage.put(voteKey, true);
    await this.ctx.storage.setAlarm(state.scheduledEvents[0]?.dueAt ?? nowMs() + this.pollWindowMs);
    await this.saveState(state);
    return this.buildSnapshot(state);
  }

  async attachReadySong(song: ReadySong): Promise<PlaybackSnapshot> {
    const state = await this.ensureState();
    const alreadyQueued = [
      state.currentSong.voteId,
      state.nextSong.voteId,
      ...state.readySongs.map((entry) => entry.voteId),
    ].includes(song.voteId);

    if (!alreadyQueued) {
      state.readySongs.push(song);
      state.readySongs = state.readySongs.sort((a, b) => a.createdAt - b.createdAt);
    }

    if (!state.currentSong.voteId) {
      this.promoteReadySong(state);
      await this.openNextPoll(state);
    } else if (!state.nextSong.voteId) {
      const next = state.readySongs.shift() ?? null;
      state.nextSong = next
        ? { voteId: next.voteId, durationMs: next.durationMs, audioUrl: next.audioUrl }
        : { voteId: null, durationMs: null, audioUrl: null };
    }

    await this.scheduleFromState(state);
    await this.saveState(state);
    return this.buildSnapshot(state);
  }

  async seedState(payload: SeedPayload): Promise<PlaybackSnapshot> {
    const state = await this.ensureState();
    if (payload.currentSong) {
      state.currentSong = payload.currentSong;
    }
    if (payload.nextSong) {
      state.nextSong = payload.nextSong;
    }
    if (payload.poll) {
      state.poll = {
        ...state.poll,
        ...payload.poll,
        tallies: payload.poll.tallies ?? state.poll.tallies,
        options: payload.poll.options ?? state.poll.options,
      };
    }
    await this.scheduleFromState(state);
    await this.saveState(state);
    return this.buildSnapshot(state);
  }

  async alarm(): Promise<void> {
    const state = await this.ensureState();
    const dueAt = nowMs();
    const due = state.scheduledEvents.filter((event) => event.dueAt <= dueAt);
    state.scheduledEvents = state.scheduledEvents.filter((event) => event.dueAt > dueAt);

    for (const event of due) {
      if (event.type === "vote_close") {
        await this.closePoll(state);
      }
      if (event.type === "song_end") {
        await this.rotateSong(state);
      }
    }

    await this.scheduleFromState(state);
    await this.saveState(state);
  }
}
