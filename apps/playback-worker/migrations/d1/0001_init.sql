CREATE TABLE IF NOT EXISTS polls {
  id TEXT PRIMARY KEY,
  options TEXT[] NOT NULL,
  start_at INTEGER NOT NULL,
  end_at INTEGER NOT NULL,
  is_open BOOLEAN NOT NULL DEFAULT TRUE,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
}


CREATE TABLE IF NOT EXISTS poll_votes {
  id TEXT PRIMARY KEY,
  poll_id TEXT NOT NULL,
  option TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
}


CREATE TABLE IF NOT EXISTS songs (
  id TEXT FOREIGN KEY REFERENCES polls(id),
  status TEXT NOT NULL CHECK (status IN ('ready', 'queued', 'played')),
  duration_ms INTEGER NOT NULL CHECK (duration_ms > 0),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);


CREATE INDEX IF NOT EXISTS idx_songs_status_created_at ON songs(status, created_at DESC) WHERE status = 'ready';
CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_id_option ON poll_votes(poll_id, option);
