import type { D1Database } from "@cloudflare/workers-types";
import type { GenerationReadyPayload, PlaybackSnapshot, ReadySong } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

export async function listReadySongs(db: D1Database): Promise<ReadySong[]> {
  const result = await db
    .prepare(
      `SELECT vote_id, duration_ms, public_url, winner_option, ready_at
       FROM songs
       WHERE status = 'ready'
       ORDER BY ready_at ASC`,
    )
    .all<Record<string, string | number | null>>();

  return (result.results ?? []).flatMap((row) => {
    if (!row.vote_id || !row.duration_ms || !row.public_url) {
      return [];
    }
    return [
      {
        voteId: String(row.vote_id),
        durationMs: Number(row.duration_ms),
        audioUrl: String(row.public_url),
        winnerOption: row.winner_option ? String(row.winner_option) : null,
        createdAt: Date.parse(String(row.ready_at ?? nowIso())),
      },
    ];
  });
}

export async function upsertPollRound(
  db: D1Database,
  input: {
    voteId: string;
    stationId: string;
    openedAt: string;
    status: string;
    nextVoteId?: string | null;
    winnerOption?: string | null;
    closedAt?: string | null;
    version: number;
  },
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO poll_rounds (vote_id, station_id, opened_at, closed_at, status, winner_option, next_vote_id, version)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(vote_id) DO UPDATE SET
         closed_at = excluded.closed_at,
         status = excluded.status,
         winner_option = excluded.winner_option,
         next_vote_id = excluded.next_vote_id,
         version = excluded.version`,
    )
    .bind(
      input.voteId,
      input.stationId,
      input.openedAt,
      input.closedAt ?? null,
      input.status,
      input.winnerOption ?? null,
      input.nextVoteId ?? null,
      input.version,
    )
    .run();
}

export async function recordGenerationQueued(
  db: D1Database,
  voteId: string,
  workflowInstanceId: string,
  externalJobId: string | null,
): Promise<void> {
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO generation_jobs (vote_id, workflow_instance_id, external_job_id, status, created_at, updated_at)
       VALUES (?, ?, ?, 'queued', ?, ?)
       ON CONFLICT(vote_id) DO UPDATE SET
         workflow_instance_id = excluded.workflow_instance_id,
         external_job_id = excluded.external_job_id,
         status = 'queued',
         updated_at = excluded.updated_at`,
    )
    .bind(voteId, workflowInstanceId, externalJobId, now, now)
    .run();
}

export async function recordGenerationCompleted(
  db: D1Database,
  payload: GenerationReadyPayload,
): Promise<void> {
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO songs (vote_id, status, duration_ms, r2_key, public_url, winner_option, created_at, ready_at)
       VALUES (?, 'ready', ?, ?, ?, ?, ?, ?)
       ON CONFLICT(vote_id) DO UPDATE SET
         status = 'ready',
         duration_ms = excluded.duration_ms,
         r2_key = excluded.r2_key,
         public_url = excluded.public_url,
         winner_option = excluded.winner_option,
         ready_at = excluded.ready_at`,
    )
    .bind(
      payload.voteId,
      payload.durationMs,
      payload.r2Key,
      payload.publicUrl,
      payload.winnerOption ?? null,
      now,
      now,
    )
    .run();

  await db
    .prepare(
      `INSERT INTO generation_jobs (vote_id, workflow_instance_id, external_job_id, status, callback_received_at, created_at, updated_at)
       VALUES (?, ?, ?, 'ready', ?, ?, ?)
       ON CONFLICT(vote_id) DO UPDATE SET
         external_job_id = excluded.external_job_id,
         status = 'ready',
         callback_received_at = excluded.callback_received_at,
         updated_at = excluded.updated_at`,
    )
    .bind(payload.voteId, payload.workflowInstanceId, payload.externalJobId ?? null, now, now, now)
    .run();
}

export async function recordGenerationFailure(
  db: D1Database,
  voteId: string,
  workflowInstanceId: string,
  reason: string,
): Promise<void> {
  const now = nowIso();
  await db
    .prepare(
      `INSERT INTO generation_jobs (vote_id, workflow_instance_id, status, failure_reason, created_at, updated_at)
       VALUES (?, ?, 'errored', ?, ?, ?)
       ON CONFLICT(vote_id) DO UPDATE SET
         status = 'errored',
         failure_reason = excluded.failure_reason,
         updated_at = excluded.updated_at`,
    )
    .bind(voteId, workflowInstanceId, reason, now, now)
    .run();
}

export async function snapshotToPollRows(db: D1Database, snapshot: PlaybackSnapshot): Promise<void> {
  if (!snapshot.poll.voteId) {
    return;
  }

  const openedAt = snapshot.currentSong.startAt
    ? new Date(snapshot.currentSong.startAt).toISOString()
    : nowIso();

  const closedAt = snapshot.poll.status === "CLOSED" && snapshot.poll.endAt
    ? new Date(snapshot.poll.endAt).toISOString()
    : null;

  await upsertPollRound(db, {
    voteId: snapshot.poll.voteId,
    stationId: "main",
    openedAt,
    closedAt,
    status: snapshot.poll.status,
    winnerOption: snapshot.poll.winnerOption,
    version: snapshot.poll.version,
  });
}
