/**
 * D1 access. Every query is scoped by `user_id` — the bot is shareable, and one
 * person's ledger must never appear in another's summary.
 *
 * Rows are only ever added. Deletes set `deleted_at`; corrections add a row that
 * `supersedes` the old one. `LIVE` is the filter that hides both.
 */

const LIVE = "deleted_at IS NULL";

/**
 * Record that a webhook event has been handled.
 * @returns {Promise<boolean>} false when it was already handled — skip it.
 */
export async function claimEvent(db, eventId, nowIso) {
  const result = await db
    .prepare("INSERT OR IGNORE INTO processed_events (event_id, seen_at) VALUES (?, ?)")
    .bind(eventId, nowIso)
    .run();
  return result.meta.changes > 0;
}

/** Drop event ids older than `days` so the table does not grow without bound. */
export async function pruneEvents(db, cutoffIso) {
  await db.prepare("DELETE FROM processed_events WHERE seen_at < ?").bind(cutoffIso).run();
}

/**
 * Insert parsed entries.
 * @returns {Promise<string[]>} the new row ids, in the order given.
 */
export async function insertEntries(db, userId, entries, nowIso) {
  const ids = [];
  const statements = entries.map((entry) => {
    const id = crypto.randomUUID();
    ids.push(id);
    // Money rows carry `amount`, calorie rows carry `kcal`; the other stays
    // NULL so no row is ever ambiguous about its unit.
    return db
      .prepare(
        `INSERT INTO entries
           (id, user_id, type, raw, amount, currency, label, category,
            occurred_at, local_date, created_at, parser, needs_confirm,
            kcal, direction, duration_min)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        id, userId, entry.type, entry.raw, entry.amount ?? null,
        entry.currency ?? "THB", entry.label, entry.category ?? null,
        entry.occurredAt, entry.localDate, nowIso, entry.parser,
        entry.needsConfirm ? 1 : 0,
        entry.kcal ?? null, entry.direction ?? null, entry.durationMin ?? null,
      );
  });
  if (statements.length > 0) await db.batch(statements);
  return ids;
}

// ---- learned dishes ---------------------------------------------------------

/** Look up what the user has already told the bot about a dish. */
export async function recallFood(db, userId, name) {
  const row = await db
    .prepare("SELECT kcal, direction FROM food_memory WHERE user_id = ? AND name = ?")
    .bind(userId, name)
    .first();
  return row ?? null;
}

/** Teach the bot a dish, or correct one it already knows. */
export async function rememberFood(db, userId, name, kcal, direction, nowIso) {
  await db
    .prepare(
      `INSERT INTO food_memory (user_id, name, kcal, direction, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (user_id, name)
       DO UPDATE SET kcal = excluded.kcal,
                     direction = excluded.direction,
                     updated_at = excluded.updated_at`,
    )
    .bind(userId, name, kcal, direction, nowIso)
    .run();
}

/** @returns {Promise<boolean>} false when nothing was stored under that name. */
export async function forgetFood(db, userId, name) {
  const result = await db
    .prepare("DELETE FROM food_memory WHERE user_id = ? AND name = ?")
    .bind(userId, name)
    .run();
  return result.meta.changes > 0;
}

export async function listFoods(db, userId, limit = 30) {
  const { results } = await db
    .prepare(
      `SELECT name, kcal, direction FROM food_memory
        WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?`,
    )
    .bind(userId, limit)
    .all();
  return results ?? [];
}

// ---- settings ---------------------------------------------------------------

export async function getGoal(db, userId) {
  const row = await db
    .prepare("SELECT daily_kcal_goal FROM user_settings WHERE user_id = ?")
    .bind(userId)
    .first();
  return row?.daily_kcal_goal ?? null;
}

export async function setGoal(db, userId, kcal, nowIso) {
  await db
    .prepare(
      `INSERT INTO user_settings (user_id, daily_kcal_goal, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT (user_id)
       DO UPDATE SET daily_kcal_goal = excluded.daily_kcal_goal,
                     updated_at = excluded.updated_at`,
    )
    .bind(userId, kcal, nowIso)
    .run();
}

/** Most recent live entries, newest first. */
export async function recentEntries(db, userId, limit = 10) {
  const { results } = await db
    .prepare(
      `SELECT * FROM entries
        WHERE user_id = ? AND ${LIVE}
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?`,
    )
    .bind(userId, limit)
    .all();
  return results ?? [];
}

/** Soft-delete one entry. Returns the row that was removed, or null. */
export async function deleteEntry(db, userId, entryId, nowIso) {
  const row = await db
    .prepare(`SELECT * FROM entries WHERE id = ? AND user_id = ? AND ${LIVE}`)
    .bind(entryId, userId)
    .first();
  if (!row) return null;
  await db
    .prepare("UPDATE entries SET deleted_at = ? WHERE id = ? AND user_id = ?")
    .bind(nowIso, entryId, userId)
    .run();
  return row;
}

/**
 * Correct an entry's amount by superseding it, keeping the original readable.
 * @returns {Promise<object|null>} the replacement row.
 */
export async function amendAmount(db, userId, entryId, amount, nowIso) {
  const row = await db
    .prepare(`SELECT * FROM entries WHERE id = ? AND user_id = ? AND ${LIVE}`)
    .bind(entryId, userId)
    .first();
  if (!row) return null;

  // The figure goes back into whichever column this row uses, so correcting a
  // calorie entry never leaves a stray baht amount behind.
  const isCalorie = row.type === "calorie";
  const newId = crypto.randomUUID();
  await db.batch([
    db
      .prepare("UPDATE entries SET deleted_at = ? WHERE id = ?")
      .bind(nowIso, entryId),
    db
      .prepare(
        `INSERT INTO entries
           (id, user_id, type, raw, amount, currency, label, category,
            occurred_at, local_date, created_at, parser, needs_confirm,
            kcal, direction, duration_min, supersedes)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 0, ?, ?, ?, ?)`,
      )
      .bind(
        newId, userId, row.type, row.raw, isCalorie ? null : amount, row.currency,
        row.label, row.category, row.occurred_at, row.local_date, nowIso,
        isCalorie ? amount : null, row.direction, row.duration_min, entryId,
      ),
  ]);
  return {
    ...row,
    id: newId,
    amount: isCalorie ? null : amount,
    kcal: isCalorie ? amount : null,
    supersedes: entryId,
  };
}

/** Totals and a per-entry breakdown for one Bangkok date. */
export async function daySummary(db, userId, localDate) {
  const { results } = await db
    .prepare(
      `SELECT type, label, amount, kcal, direction, duration_min FROM entries
        WHERE user_id = ? AND local_date = ? AND ${LIVE}
        ORDER BY created_at ASC`,
    )
    .bind(userId, localDate)
    .all();
  return summarise(results ?? []);
}

/** Totals for a Bangkok month, plus the biggest spending categories. */
export async function monthSummary(db, userId, month) {
  const { results } = await db
    .prepare(
      `SELECT type, label, amount, category, kcal, direction FROM entries
        WHERE user_id = ? AND local_date LIKE ? AND ${LIVE}`,
    )
    .bind(userId, `${month}-%`)
    .all();

  const rows = results ?? [];
  const byCategory = new Map();
  for (const row of rows) {
    if (row.type !== "expense") continue;
    const key = row.category ?? "อื่น ๆ";
    byCategory.set(key, (byCategory.get(key) ?? 0) + row.amount);
  }
  return {
    ...summarise(rows),
    topCategories: [...byCategory.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5),
  };
}

/** How many distinct days in the month carry a calorie entry. */
export async function calorieDayCount(db, userId, month) {
  const row = await db
    .prepare(
      `SELECT COUNT(DISTINCT local_date) AS days FROM entries
        WHERE user_id = ? AND local_date LIKE ? AND ${LIVE} AND type = 'calorie'`,
    )
    .bind(userId, `${month}-%`)
    .first();
  return row?.days ?? 0;
}

function summarise(rows) {
  let expense = 0;
  let income = 0;
  let intake = 0;
  let burn = 0;

  for (const row of rows) {
    if (row.type === "expense") expense += row.amount;
    else if (row.type === "income") income += row.amount;
    else if (row.type === "calorie") {
      if (row.direction === "burn") burn += row.kcal;
      else intake += row.kcal;
    }
  }

  const moneyRows = rows.filter((row) => row.type === "expense" || row.type === "income");
  const calorieRows = rows.filter((row) => row.type === "calorie");

  return {
    expense,
    income,
    net: income - expense,
    intake,
    burn,
    netKcal: intake - burn,
    count: rows.length,
    rows: moneyRows,
    calorieRows,
  };
}
