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
    return db
      .prepare(
        `INSERT INTO entries
           (id, user_id, type, raw, amount, currency, label, category,
            occurred_at, local_date, created_at, parser, needs_confirm)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        id, userId, entry.type, entry.raw, entry.amount, entry.currency,
        entry.label, entry.category, entry.occurredAt, entry.localDate,
        nowIso, entry.parser, entry.needsConfirm ? 1 : 0,
      );
  });
  if (statements.length > 0) await db.batch(statements);
  return ids;
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

  const newId = crypto.randomUUID();
  await db.batch([
    db
      .prepare("UPDATE entries SET deleted_at = ? WHERE id = ?")
      .bind(nowIso, entryId),
    db
      .prepare(
        `INSERT INTO entries
           (id, user_id, type, raw, amount, currency, label, category,
            occurred_at, local_date, created_at, parser, needs_confirm, supersedes)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 0, ?)`,
      )
      .bind(
        newId, userId, row.type, row.raw, amount, row.currency, row.label,
        row.category, row.occurred_at, row.local_date, nowIso, entryId,
      ),
  ]);
  return { ...row, id: newId, amount, supersedes: entryId };
}

/** Totals and a per-entry breakdown for one Bangkok date. */
export async function daySummary(db, userId, localDate) {
  const { results } = await db
    .prepare(
      `SELECT type, label, amount FROM entries
        WHERE user_id = ? AND local_date = ? AND ${LIVE}
          AND type IN ('expense', 'income')
        ORDER BY created_at ASC`,
    )
    .bind(userId, localDate)
    .all();
  return summarise(results ?? []);
}

/** Totals for a Bangkok month, plus the biggest categories. */
export async function monthSummary(db, userId, month) {
  const { results } = await db
    .prepare(
      `SELECT type, label, amount, category FROM entries
        WHERE user_id = ? AND local_date LIKE ? AND ${LIVE}
          AND type IN ('expense', 'income')`,
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

function summarise(rows) {
  let expense = 0;
  let income = 0;
  for (const row of rows) {
    if (row.type === "expense") expense += row.amount;
    else if (row.type === "income") income += row.amount;
  }
  return { expense, income, net: income - expense, count: rows.length, rows };
}
