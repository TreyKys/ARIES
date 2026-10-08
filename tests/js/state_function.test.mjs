// Integration test for netlify/functions/state.mjs.
//
// It runs the real handler against a real blob store (the one @netlify/blobs
// ships for local use), so the auth rules, the JSON validation and the
// store/fetch round trip are all exercised rather than assumed. This is the
// piece the hosted monitor depends on, and a mistake in it is either a
// dashboard that shows nothing or account state served to anyone.
import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { BlobsServer } from "@netlify/blobs/server";

const WRITE = "write-token-aaaaaaaaaaaa";
const READ = "read-token-bbbbbbbbbbbbb";
const SITE = "test-site";
const TOKEN = "test-blobs-token";

const dir = await mkdtemp(join(tmpdir(), "aries-blobs-"));
const server = new BlobsServer({ directory: dir, token: TOKEN, port: 0 });
const { port } = await server.start();

process.env.ARIES_WRITE_TOKEN = WRITE;
process.env.ARIES_READ_TOKEN = READ;
process.env.NETLIFY_BLOBS_CONTEXT = Buffer.from(JSON.stringify({
  edgeURL: `http://localhost:${port}`,
  uncachedEdgeURL: `http://localhost:${port}`,
  siteID: SITE,
  token: TOKEN,
})).toString("base64");

const { default: handler } = await import("../../netlify/functions/state.mjs");

const url = "https://example.netlify.app/api/state";
const post = (body, auth) => handler(new Request(url, {
  method: "POST", body,
  headers: auth ? { authorization: `Bearer ${auth}` } : {},
}));
const get = (k) => handler(new Request(url, {
  headers: k ? { "x-aries-key": k } : {},
}));

const snapshot = JSON.stringify({ equity: 25123.45, n_trades: 3, trades: [] });
let failed = 0;
async function check(name, fn) {
  try { await fn(); console.log(`  ok   ${name}`); }
  catch (e) { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }
}

await check("GET without a key is refused", async () => {
  const r = await get();
  assert.equal(r.status, 401);
  // the refusal must not leak what the key is
  assert.ok(!(await r.text()).includes(READ));
});

await check("GET with the WRITE token is refused", async () => {
  assert.equal((await get(WRITE)).status, 401);
});

await check("GET before any push reports no snapshot", async () => {
  assert.equal((await get(READ)).status, 404);
});

await check("POST without a token is refused", async () => {
  assert.equal((await post(snapshot)).status, 401);
});

await check("POST with the READ token is refused", async () => {
  assert.equal((await post(snapshot, READ)).status, 401);
});

await check("POST of non-JSON is rejected, not stored", async () => {
  assert.equal((await post("this is not json", WRITE)).status, 400);
  assert.equal((await get(READ)).status, 404);
});

await check("POST then GET round-trips the snapshot", async () => {
  assert.equal((await post(snapshot, WRITE)).status, 204);
  const r = await get(READ);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.deepEqual(await r.json(), JSON.parse(snapshot));
});

await check("a second POST overwrites the first", async () => {
  await post(JSON.stringify({ equity: 99 }), WRITE);
  assert.equal((await get(READ)).status, 200);
  assert.equal((await (await get(READ)).json()).equity, 99);
});

await check("an oversized payload is refused", async () => {
  const big = JSON.stringify({ pad: "x".repeat(4_000_001) });
  assert.equal((await post(big, WRITE)).status, 413);
});

await check("a near-miss token is refused", async () => {
  assert.equal((await get(READ.slice(0, -1) + "c")).status, 401);
  assert.equal((await get(READ.slice(0, -1))).status, 401);
});

await check("other methods are refused", async () => {
  const r = await handler(new Request(url, { method: "DELETE" }));
  assert.equal(r.status, 405);
});

await check("no tokens configured means no access at all", async () => {
  delete process.env.ARIES_READ_TOKEN;
  delete process.env.ARIES_WRITE_TOKEN;
  assert.equal((await get(READ)).status, 503);
  assert.equal((await post(snapshot, WRITE)).status, 503);
  process.env.ARIES_READ_TOKEN = READ;
  process.env.ARIES_WRITE_TOKEN = WRITE;
});

await server.stop();
console.log(failed ? `\n${failed} FAILED` : "\nall state-function tests passed");
process.exit(failed ? 1 : 0);
