/**
 * A D1-shaped wrapper around node:sqlite, so the database layer can be tested
 * for real instead of against a mock that agrees with whatever the code does.
 *
 * D1 is SQLite underneath, so the SQL exercised here is the SQL that runs in
 * production. Only the calling convention differs, and that is what this maps:
 * prepare/bind/run/all/first/batch.
 */

import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

class Statement {
  constructor(sqlite, sql) {
    this.sqlite = sqlite;
    this.sql = sql;
    this.params = [];
  }

  bind(...params) {
    this.params = params;
    return this;
  }

  async run() {
    const result = this.sqlite.prepare(this.sql).run(...this.params);
    return { meta: { changes: Number(result.changes) } };
  }

  async all() {
    return { results: this.sqlite.prepare(this.sql).all(...this.params) };
  }

  async first() {
    return this.sqlite.prepare(this.sql).get(...this.params) ?? null;
  }
}

class D1Stub {
  constructor(sqlite) {
    this.sqlite = sqlite;
  }

  prepare(sql) {
    return new Statement(this.sqlite, sql);
  }

  async batch(statements) {
    const out = [];
    for (const statement of statements) out.push(await statement.run());
    return out;
  }
}

import { readdirSync } from "node:fs";

const MIGRATIONS_DIR = fileURLToPath(new URL("../../migrations/", import.meta.url));

/**
 * A fresh in-memory database with every migration applied, in filename order —
 * the same order wrangler applies them, so a migration that only works on an
 * empty database fails here too.
 */
export function freshDb() {
  const sqlite = new DatabaseSync(":memory:");
  for (const file of readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith(".sql")).sort()) {
    sqlite.exec(readFileSync(MIGRATIONS_DIR + file, "utf8"));
  }
  return new D1Stub(sqlite);
}
