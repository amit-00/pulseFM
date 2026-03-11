CREATE TABLE IF NOT EXISTS polls (
  id TEXT PRIMARY KEY,
  options TEXT NOT NULL CHECK (json_valid(options) AND json_type(options) = 'array'),
  start_at INTEGER NOT NULL CHECK (start_at > 0),
  end_at INTEGER NOT NULL CHECK (end_at >= start_at),
  is_open INTEGER NOT NULL DEFAULT 1 CHECK (is_open IN (0, 1)),
  winner TEXT,
  created_at INTEGER NOT NULL CHECK (created_at > 0),
  updated_at INTEGER NOT NULL CHECK (updated_at > 0)
);

CREATE TABLE IF NOT EXISTS poll_votes (
  id TEXT PRIMARY KEY,
  poll_id TEXT NOT NULL,
  user_id TEXT NOT NULL CHECK (length(trim(user_id)) > 0),
  option TEXT NOT NULL CHECK (length(trim(option)) > 0),
  created_at INTEGER NOT NULL CHECK (created_at > 0),
  updated_at INTEGER NOT NULL CHECK (updated_at > 0),
  FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
  UNIQUE (poll_id, user_id)
);

CREATE TABLE IF NOT EXISTS songs (
  id TEXT PRIMARY KEY REFERENCES polls(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('ready', 'queued', 'played')),
  duration_ms INTEGER NOT NULL CHECK (duration_ms > 0),
  created_at INTEGER NOT NULL CHECK (created_at > 0),
  updated_at INTEGER NOT NULL CHECK (updated_at > 0)
);

CREATE TRIGGER IF NOT EXISTS trg_validate_poll_vote_insert
BEFORE INSERT ON poll_votes
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1
  FROM polls p, json_each(p.options) je
  WHERE p.id = NEW.poll_id
    AND p.is_open = 1
    AND je.value = NEW.option
)
BEGIN
  SELECT RAISE(ABORT, 'invalid_vote');
END;

CREATE TRIGGER IF NOT EXISTS trg_validate_poll_vote_update
BEFORE UPDATE OF poll_id, option ON poll_votes
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1
  FROM polls p, json_each(p.options) je
  WHERE p.id = NEW.poll_id
    AND p.is_open = 1
    AND je.value = NEW.option
)
BEGIN
  SELECT RAISE(ABORT, 'invalid_vote');
END;

CREATE INDEX IF NOT EXISTS idx_songs_status_created_at
  ON songs(status, created_at DESC)
  WHERE status = 'ready';
CREATE INDEX IF NOT EXISTS idx_poll_votes_poll_id_option
  ON poll_votes(poll_id, option);
