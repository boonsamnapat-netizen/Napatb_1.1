/**
 * Cloudflare Worker entry point for the LINE assistant bot.
 *
 * Round 1 handles income and expenses. Calorie counting and to-do reminders are
 * recognised and politely declined rather than mis-filed — see `parser/index.js`
 * for why that guard matters.
 *
 * The webhook answers 200 for anything that carries a valid signature, even when
 * handling an individual event fails. LINE redelivers on a non-200, and a
 * redelivered expense that slipped past the idempotency table would double the
 * user's totals — a wrong number nobody would notice. A dropped reply is the
 * cheaper failure.
 */

import { parseMessage } from "./parser/index.js";
import { verifySignature, reply } from "./line.js";
import { localDate } from "./lib/thaidate.js";
import * as db from "./db.js";
import * as fmt from "./format.js";

/** LINE posts this token when you press "Verify" in the console. */
const VERIFY_TOKEN = "00000000000000000000000000000000";

export default {
  async fetch(request, env, ctx) {
    if (request.method === "GET") {
      return new Response("napatb linebot: ok", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }
    if (!env.LINE_CHANNEL_SECRET || !env.LINE_CHANNEL_ACCESS_TOKEN) {
      console.error("LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN not configured");
      return new Response("not configured", { status: 500 });
    }

    // Read the body as text: the signature covers the exact bytes sent, so it
    // has to be checked before any JSON parsing.
    const body = await request.text();
    const signature = request.headers.get("x-line-signature");
    if (!(await verifySignature(env.LINE_CHANNEL_SECRET, body, signature))) {
      return new Response("bad signature", { status: 401 });
    }

    let payload;
    try {
      payload = JSON.parse(body);
    } catch {
      return new Response("bad json", { status: 400 });
    }

    const events = Array.isArray(payload.events) ? payload.events : [];
    // Answer LINE now and finish the work after: reply tokens expire in about a
    // minute, but the webhook itself should return straight away.
    ctx.waitUntil(
      Promise.all(events.map((event) => handleEvent(event, env).catch(
        (error) => console.error("event failed:", error?.stack ?? error),
      ))),
    );
    return new Response("ok");
  },

  /**
   * Cron entry point. Reminders will hang off this once the to-do round lands;
   * for now it only keeps the idempotency table from growing forever.
   */
  async scheduled(event, env, ctx) {
    const cutoff = new Date(Date.now() - 7 * 86_400_000).toISOString();
    ctx.waitUntil(db.pruneEvents(env.DB, cutoff));
  },
};

async function handleEvent(event, env) {
  const token = env.LINE_CHANNEL_ACCESS_TOKEN;

  if (event.type === "follow") {
    return reply(token, event.replyToken, fmt.help());
  }
  if (event.type !== "message" || event.message?.type !== "text") return;
  if (event.replyToken === VERIFY_TOKEN) return; // console "Verify" ping

  // Group chats share one ledger keyed by the group; 1:1 chats key by user.
  const owner = event.source?.userId ?? event.source?.groupId ?? event.source?.roomId;
  if (!owner) return;

  const now = new Date();
  const nowIso = now.toISOString();

  // LINE redelivers events it could not confirm. Claim the id first so a retry
  // cannot file the same expense twice.
  if (event.webhookEventId) {
    const fresh = await db.claimEvent(env.DB, event.webhookEventId, nowIso);
    if (!fresh) return;
  }

  const text = await respond(event.message.text, owner, now, nowIso, env);
  if (text) await reply(token, event.replyToken, text);
}

/**
 * Work out the answer to one message.
 * @returns {Promise<string|null>} reply text, or null to stay quiet.
 */
async function respond(messageText, owner, now, nowIso, env) {
  const today = localDate(now);
  const result = parseMessage(messageText, now);

  switch (result.kind) {
    case "command":
      return runCommand(result, owner, now, nowIso, today, env);

    case "unsupported":
      return fmt.unsupported(result.feature);

    case "unparsed":
      return fmt.unparsed();

    case "entries": {
      await db.insertEntries(env.DB, owner, result.entries, nowIso);
      // Totals for the day the entries landed on, which is not always today.
      const totalsDate = result.entries[result.entries.length - 1].localDate;
      const totals = await db.daySummary(env.DB, owner, totalsDate);
      const lines = [fmt.savedEntries(result.entries, totals, totalsDate, today)];
      if (result.ignoredCalories) lines.push(fmt.caloriesIgnored());
      return lines.join("\n");
    }

    default:
      return null;
  }
}

async function runCommand(command, owner, now, nowIso, today, env) {
  switch (command.name) {
    case "help":
      return fmt.help();

    case "summary_day":
      return fmt.daySummary(await db.daySummary(env.DB, owner, today), today);

    case "summary_month": {
      const month = today.slice(0, 7);
      return fmt.monthSummary(await db.monthSummary(env.DB, owner, month), month);
    }

    case "delete": {
      const recent = await db.recentEntries(env.DB, owner, command.index);
      const target = recent[command.index - 1];
      if (!target) return fmt.nothingToDelete();
      const removed = await db.deleteEntry(env.DB, owner, target.id, nowIso);
      return removed ? fmt.deleted(removed) : fmt.nothingToDelete();
    }

    case "amend": {
      const [latest] = await db.recentEntries(env.DB, owner, 1);
      if (!latest) return fmt.nothingToDelete();
      const updated = await db.amendAmount(env.DB, owner, latest.id, command.amount, nowIso);
      return updated ? fmt.amended(updated, latest.amount) : fmt.nothingToDelete();
    }

    default:
      return null;
  }
}

export { respond as _respond };
