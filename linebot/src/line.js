/**
 * LINE Messaging API client.
 *
 * Two things worth knowing about the platform, because they shape this file:
 *
 * 1. The webhook URL is public. Anyone can POST to it, so every request must be
 *    checked against the channel secret before a single byte of it is trusted.
 * 2. Replies are free and unmetered; pushes count against the monthly message
 *    quota, and once that quota is spent LINE *drops* the message rather than
 *    billing for it. So: answer with `reply` wherever a reply is possible, and
 *    treat `push` as a scarce resource for the reminder round.
 *
 * A reply token is single-use and expires about a minute after the webhook
 * arrives, which is why the handler answers inline rather than queueing work.
 */

const API = "https://api.line.me/v2/bot";

/**
 * Verify the `x-line-signature` header against the raw request body.
 * Uses crypto.subtle.verify so the comparison is constant-time.
 *
 * @param {string} channelSecret
 * @param {string} body raw request body, exactly as received
 * @param {string|null} signature base64 header value
 */
export async function verifySignature(channelSecret, body, signature) {
  if (!signature) return false;

  let signatureBytes;
  try {
    signatureBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  } catch {
    return false; // not valid base64 — not from LINE
  }

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(channelSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  return crypto.subtle.verify("HMAC", key, signatureBytes, new TextEncoder().encode(body));
}

/** LINE rejects any text message longer than 5000 characters. */
const MAX_TEXT = 5000;

function textMessages(texts) {
  return texts
    .filter((text) => text && text.trim())
    .slice(0, 5) // LINE accepts at most 5 message objects per call
    .map((text) => ({ type: "text", text: text.slice(0, MAX_TEXT) }));
}

async function post(token, path, payload) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    // Surfaced in `wrangler tail`. Never thrown: a failed reply must not turn
    // into a non-200 webhook response, or LINE will redeliver the whole event.
    console.error(`LINE ${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.ok;
}

/** Answer the message that triggered this webhook. Free, and does not count against quota. */
export function reply(token, replyToken, texts) {
  const messages = textMessages(Array.isArray(texts) ? texts : [texts]);
  if (messages.length === 0) return Promise.resolve(true);
  return post(token, "/message/reply", { replyToken, messages });
}

/**
 * Send to a user unprompted. Counts against the monthly quota — reserve it for
 * reminders, which cannot use a reply token.
 */
export function push(token, to, texts) {
  const messages = textMessages(Array.isArray(texts) ? texts : [texts]);
  if (messages.length === 0) return Promise.resolve(true);
  return post(token, "/message/push", { to, messages });
}
