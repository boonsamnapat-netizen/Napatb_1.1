-- Ledger for the LINE assistant bot.
--
-- Rows are never edited in place. A correction writes a new row pointing at the
-- old one through `supersedes` and stamps the old one's `deleted_at`, so the
-- history of what was typed survives every fix — and `raw` always holds the
-- original message, which is the only reliable way to re-read an entry when the
-- parser turns out to have been wrong.
--
-- `type` is open to 'calorie' and 'task' so the later rounds do not need a
-- second table; only 'expense' and 'income' are written today.

CREATE TABLE IF NOT EXISTS entries (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('expense', 'income', 'calorie', 'task')),
  raw           TEXT NOT NULL,
  amount        REAL,
  currency      TEXT NOT NULL DEFAULT 'THB',
  label         TEXT NOT NULL DEFAULT '',
  category      TEXT,
  -- ISO-8601 carrying the +07:00 offset, so a reader never has to guess.
  occurred_at   TEXT NOT NULL,
  -- The Bangkok calendar date, denormalised so daily and monthly totals are a
  -- plain string comparison instead of a timezone conversion per row.
  local_date    TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  parser        TEXT NOT NULL DEFAULT 'regex',
  needs_confirm INTEGER NOT NULL DEFAULT 0,
  deleted_at    TEXT,
  supersedes    TEXT REFERENCES entries(id)
);

CREATE INDEX IF NOT EXISTS idx_entries_user_date ON entries (user_id, local_date);
CREATE INDEX IF NOT EXISTS idx_entries_user_created ON entries (user_id, created_at DESC);

-- LINE redelivers a webhook when it does not get a prompt 200, so the same
-- message can arrive more than once. Without this table a retry would file the
-- expense a second time — the failure mode is silent and the totals just drift.
CREATE TABLE IF NOT EXISTS processed_events (
  event_id TEXT PRIMARY KEY,
  seen_at  TEXT NOT NULL
);
