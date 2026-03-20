CREATE TABLE IF NOT EXISTS songs (
  vote_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  duration_ms INTEGER,
  r2_key TEXT,
  public_url TEXT,
  winner_option TEXT,
  created_at TEXT NOT NULL,
  ready_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_songs_status_ready_at
  ON songs(status, ready_at);

CREATE TABLE IF NOT EXISTS poll_rounds (
  vote_id TEXT PRIMARY KEY,
  station_id TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  status TEXT NOT NULL,
  winner_option TEXT,
  next_vote_id TEXT,
  version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_poll_rounds_station_opened_at
  ON poll_rounds(station_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS generation_jobs (
  vote_id TEXT PRIMARY KEY,
  workflow_instance_id TEXT NOT NULL,
  external_job_id TEXT,
  status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  callback_received_at TEXT,
  failure_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
