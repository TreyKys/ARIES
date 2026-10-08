// End-to-end: the real ares/publish.py pushes over real HTTP into the real
// netlify/functions/state.mjs, and the stored snapshot is read back.
//
// This is the seam that nothing else covers. Both sides pass their own tests
// against their own assumptions, so a mismatch in the header name or the
// bearer format would leave a monitor that is simply always empty.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { BlobsServer } from "@netlify/blobs/server";

const WRITE = "e2e-write-token-0001";
const READ = "e2e-read-token-00002";

const dir = await mkdtemp(join(tmpdir(), "aries-e2e-"));
const blobs = new BlobsServer({ directory: dir, token: "t", port: 0 });
const { port: blobPort } = await blobs.start();

process.env.ARIES_WRITE_TOKEN = WRITE;
process.env.ARIES_READ_TOKEN = READ;
process.env.NETLIFY_BLOBS_CONTEXT = Buffer.from(JSON.stringify({
  edgeURL: `http://localhost:${blobPort}`,
  uncachedEdgeURL: `http://localhost:${blobPort}`,
  siteID: "e2e", token: "t",
})).toString("base64");

const { default: handler } = await import("../../netlify/functions/state.mjs");

// Bridge node's http server to the function's Request/Response signature,
// which is what Netlify does in production.
const api = createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const r = await handler(new Request(`http://localhost${req.url}`, {
    method: req.method,
    headers: req.headers,
    body: chunks.length ? Buffer.concat(chunks) : undefined,
  }));
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
});
const apiPort = await new Promise((ok) =>
  api.listen(0, "127.0.0.1", () => ok(api.address().port)));
const url = `http://127.0.0.1:${apiPort}/api/state`;

let failed = 0;
async function check(name, fn) {
  try { await fn(); console.log(`  ok   ${name}`); }
  catch (e) { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }
}

// Async spawn, NOT spawnSync: the bridge server runs in this same process, so
// a blocking spawn would freeze the event loop and the child's request could
// never be answered -- it would time out and look like a publisher bug.
function pushFromPython(token, extra = "") {
  const code = `
import sys
sys.path.insert(0, ".")
from ares.monitor import Monitor
from ares.publish import Publisher
p = Publisher(url=${JSON.stringify(url)}, token=${JSON.stringify(token)},
              min_interval=0)
m = Monitor(path="${dir}/local.json", strategy="combined", capital=25000.0,
            publisher=p)
m.mode = "paper"
m.connected = True
m.record_trade("MES", 2.0, 5100.25, cost=1.48)
m.record_trade("MGC", -1.0, 2401.5, cost=0.92)
m.set_positions({"MES": {"qty": 2.0, "price": 5100.25, "target": 2.0, "mult": 5.0}})
for i in range(3000):
    m.mark(25000.0 + i)
${extra}
err = p.push(m.snapshot(), force=True)
print("ERR", err)
print("PUSHES", p.pushes, "FAILURES", p.failures)
`;
  return new Promise((resolve) => {
    const child = spawn("python", ["-I", "-c", code], {
      cwd: process.cwd(),
      // The sandbox routes outbound HTTP through a proxy that cannot reach a
      // loopback port; urllib honours http_proxy for http:// URLs.
      env: { ...process.env, ARIES_STATE_URL: "", ARIES_WRITE_TOKEN: "",
             no_proxy: "127.0.0.1,localhost",
             NO_PROXY: "127.0.0.1,localhost" },
    });
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => { stdout += d; });
    child.stderr.on("data", (d) => { stderr += d; });
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
}

await check("python pushes and the function stores it", async () => {
  const r = await pushFromPython(WRITE);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /PUSHES 1 FAILURES 0/);

  const got = await fetch(url, { headers: { "x-aries-key": READ } });
  assert.equal(got.status, 200);
  const d = await got.json();
  assert.equal(d.capital, 25000);
  assert.equal(d.mode, "paper");
  assert.equal(d.connected, true);
  // 3000 curve points must arrive decimated, with both ends intact
  assert.equal(d.curve.length, 600);
  assert.equal(d.curve[d.curve.length - 1][1], 25000 + 2999);
  // positions carry the multiplier, so exposure is a real dollar figure
  assert.equal(d.gross_exposure, 2 * 5100.25 * 5);
  assert.equal(d.trades.length, 2);
  assert.equal(d.trades[0].symbol, "MGC");       // newest first
  assert.equal(d.trades[0].side, "SELL");
});

await check("a wrong write token is rejected and reported, not raised", async () => {
  const r = await pushFromPython("wrong-token-entirely");
  assert.equal(r.status, 0, "the trading loop must survive a bad token");
  assert.match(r.stdout, /PUSHES 0 FAILURES 1/);
});

await check("the read key is still required after a real push", async () => {
  assert.equal((await fetch(url)).status, 401);
  assert.equal((await fetch(url, {
    headers: { "x-aries-key": WRITE } })).status, 401);
});

api.close();
await blobs.stop();
console.log(failed ? `\n${failed} FAILED` : "\nend-to-end round trip passed");
process.exit(failed ? 1 : 0);
