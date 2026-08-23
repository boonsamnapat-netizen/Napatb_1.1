-- Calorie tracking.
--
-- Calories live in the same `entries` table as money — one ledger, one set of
-- delete/amend rules, one place to look. `kcal` is a separate column rather than
-- reusing `amount` so a row is never ambiguous about which unit it carries.
--
-- There is no built-in food table on purpose. Published calorie figures for Thai
-- dishes vary enormously by recipe and portion, and a number the bot invented
-- would be indistinguishable from one the owner measured. Instead the bot
-- remembers what it is told: `food_memory` is filled in by the user, one dish at
-- a time, and every stored figure traces back to something they typed.

ALTER TABLE entries ADD COLUMN kcal REAL;
-- 'intake' for food, 'burn' for exercise. NULL on money rows.
ALTER TABLE entries ADD COLUMN direction TEXT;
ALTER TABLE entries ADD COLUMN duration_min REAL;

-- Dish (or workout) -> calories, learned from the user and scoped to them.
CREATE TABLE IF NOT EXISTS food_memory (
  user_id    TEXT NOT NULL,
  name       TEXT NOT NULL,
  kcal       REAL NOT NULL,
  direction  TEXT NOT NULL DEFAULT 'intake',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, name)
);

CREATE TABLE IF NOT EXISTS user_settings (
  user_id         TEXT PRIMARY KEY,
  daily_kcal_goal REAL,
  updated_at      TEXT NOT NULL
);
