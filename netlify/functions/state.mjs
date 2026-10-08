// Hosted store for the ARIES monitor snapshot.
//
// Why this exists: the bot runs on a laptop, next to IB Gateway, so a hosted
// page cannot read its state file. The bot PUSHES a snapshot here and the
// monitor page PULLS it, which is what makes the dashboard reachable from a
// phone without leaving a port open at home.
//
// Two separate tokens, because the two sides need different trust:
//   ARIES_WRITE_TOKEN  only the bot has it; it can overwrite the snapshot.
//   ARIES_READ_TOKEN   goes into the browser; it can only read.
// Both are site environment variables set in the Netlify UI, never committed.
//
// This holds live account data, so there is no unauthenticated path to it.
import { getStore } from "@netlify/blobs";

const KEY = "latest";
const MAX_BYTES = 4_000_000;

const json = (body, status) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json",
               "cache-control": "no-store" },
  });

// Length-independent compare, so a token cannot be recovered one byte at a
// time from response timing.
function tokenOk(given, expected) {
  if (!expected || !given || given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < given.length; i++) {
    diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return diff === 0;
}

export default async (req) => {
  const writeToken = process.env.ARIES_WRITE_TOKEN;
  const readToken = process.env.ARIES_READ_TOKEN;
  const store = getStore("aries-state");

  if (req.method === "POST") {
    if (!writeToken) {
      return json({ error: "ARIES_WRITE_TOKEN is not set on this site" }, 503);
    }
    const bearer = (req.headers.get("authorization") || "")
      .replace(/^Bearer\s+/i, "");
    if (!tokenOk(bearer, writeToken)) {
      return json({ error: "bad write token" }, 401);
    }
    const text = await req.text();
    if (text.length > MAX_BYTES) {
      return json({ error: `snapshot too large (${text.length} bytes)` }, 413);
    }
    // Validate before storing. A stored half-snapshot would make the page
    // fail on every poll with nothing to roll back to.
    try {
      JSON.parse(text);
    } catch {
      return json({ error: "body is not valid JSON" }, 400);
    }
    await store.set(KEY, text, { metadata: { received: Date.now() } });
    return new Response(null, { status: 204, headers: { "cache-control": "no-store" } });
  }

  if (req.method === "GET") {
    if (!readToken) {
      return json({ error: "ARIES_READ_TOKEN is not set on this site" }, 503);
    }
    // Header only -- never a query parameter. A key in the query string ends
    // up in access logs, browser history and any referrer header.
    if (!tokenOk(req.headers.get("x-aries-key") || "", readToken)) {
      return json({ error: "bad or missing read key" }, 401);
    }
    const body = await store.get(KEY);
    if (!body) {
      return json({ error: "no snapshot has been pushed yet" }, 404);
    }
    return new Response(body, {
      headers: { "content-type": "application/json",
                 "cache-control": "no-store" },
    });
  }

  return json({ error: "method not allowed" }, 405);
};
