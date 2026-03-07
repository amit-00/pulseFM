CREATE TABLE IF NOT EXISTS songs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('ready', 'queued', 'played')),
  duration_ms INTEGER NOT NULL CHECK (duration_ms > 0),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_songs_status_created_at ON songs(status, created_at DESC);
