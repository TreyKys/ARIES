// Render monitor/index.html in a real browser against a real /api/state, as a
// hosted deploy would, and assert what the page actually shows.
//
// Run with:  npm run test:page   (after: npm install --no-save playwright)
//
// This is the only check that the page WORKS rather than merely parses. It
// covers the two things a hosted monitor gets wrong silently: showing stale
// data as if it were live, and rendering a log message as markup.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
// Playwright is NOT a dependency of this project -- it would be installed on
// every Netlify build for no reason. Install it when you want to run this:
//     npm install --no-save playwright
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.log("skipped: playwright is not installed "
              + "(npm install --no-save playwright)");
  process.exit(0);
}

const SNAP = {
  generated: Date.now(), started: Date.now() - 3600e3,
  strategy: "combined", mode: "paper", connected: true, last_error: null,
  capital: 25000, equity: 26500.5, pnl_abs: 1500.5, pnl_pct: 6.002,
  day_pnl_abs: -120.25, drawdown_pct: 1.84, n_positions: 2, n_trades: 2,
  gross_exposure: 51002.5, net_exposure: 38990,
  positions: {
    MES: { qty: 2, price: 5100.25, target: 2, mult: 5 },
    MGC: { qty: -1, price: 2401.5, target: -3, mult: 100 },
    MNQ: { qty: 0, price: 18000, target: 1, mult: 2 },
  },
  trades: [
    { ts: Date.now() - 60e3, symbol: "MGC", side: "SELL", qty: 1, price: 2401.5, cost: 0.92, note: "Filled" },
    { ts: Date.now() - 300e3, symbol: "MES", side: "BUY", qty: 2, price: 5100.25, cost: 1.48, note: "Filled" },
  ],
  activity: [
    { ts: Date.now() - 50e3, level: "TRADE", source: "MGC", message: "SELL 1 @ 2,401.5000" },
    { ts: Date.now() - 400e3, level: "WARN", source: "IBKR", message: "reconnecting <script>alert(1)</script>" },
    { ts: Date.now() - 900e3, level: "INFO", source: "SYSTEM", message: "start paper" },
  ],
  curve: Array.from({ length: 300 }, (_, i) => [Date.now() - (300 - i) * 60e3, 25000 + i * 5]),
};

const READ = "page-read-key";
const page_html = readFileSync("monitor/index.html", "utf8");

const srv = createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  if (u.pathname === "/api/state") {
    if (req.headers["x-aries-key"] !== READ) {
      res.writeHead(401, { "content-type": "application/json" });
      return res.end(JSON.stringify({ error: "bad or missing read key" }));
    }
    res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
    return res.end(JSON.stringify(SNAP));
  }
  if (u.pathname.startsWith("/monitor")) {
    res.writeHead(200, { "content-type": "text/html" });
    return res.end(page_html);
  }
  res.writeHead(404); res.end();
});
const port = await new Promise(ok => srv.listen(0, "127.0.0.1", () => ok(srv.address().port)));
// Served on loopback, so the page tries its local file first, gets a 404 and
// falls through to /api/state -- exercising both paths in one run.
const base = `http://127.0.0.1:${port}`;

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const ctx = await browser.newContext();
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", e => errors.push(String(e)));
page.on("console", m => {
  const t = m.text();
  // Network status noise is expected: the local-file probe 404s on a hosted
  // deploy, and the first poll 401s before the key is entered. Both are
  // handled paths. Only real script errors count.
  if (m.type() === "error" && !/Failed to load resource/.test(t)) errors.push(t);
});

let failed = 0;
const check = async (name, fn) => {
  try { await fn(); console.log(`  ok   ${name}`); }
  catch (e) { failed++; console.log(`  FAIL ${name}\n       ${e.message}`); }
};
const txt = (sel) => page.locator(sel).innerText();

await check("without a key the page asks for one", async () => {
  await page.goto(`${base}/monitor/`);
  await page.waitForSelector("#kin", { timeout: 8000 });
  assert.match(await txt("#status"), /read key required/);
  // nothing from the snapshot may be on screen before the key is given
  assert.equal(await txt("#eq"), "—");
});

await check("the key unlocks it and the numbers render", async () => {
  await page.fill("#kin", READ);
  await page.click(".keybox button");
  await page.waitForFunction(() =>
    document.getElementById("eq").textContent !== "—", null, { timeout: 8000 });
  assert.equal(await txt("#eq"), "$26,500.50");
  assert.match(await txt("#pnl"), /\$1,500\.50\s+\(6\.00%\)/);
  assert.equal(await txt("#day"), "-$120.25");
  assert.equal(await txt("#dd"), "1.84%");
  assert.equal(await txt("#np"), "2");
  assert.equal(await txt("#net"), "$38,990.00");
  assert.equal(await txt("#gross"), "gross $51,002.50");
});

await check("status shows live, and the source", async () => {
  assert.match(await txt("#status"), /live · paper · combined/);
  assert.match(await txt("#meta"), /netlify/);
});

await check("the equity line is drawn", async () => {
  assert.equal(await page.locator("#spark polyline").count(), 1);
  const pts = await page.locator("#spark polyline").getAttribute("points");
  assert.ok(pts.split(" ").length > 100, "sparkline should use the curve");
});

await check("positions show target next to actual, flagging the gap", async () => {
  const rows = await page.locator("#pos tr").count();
  assert.equal(rows, 3, "a wanted-but-unheld market must still be listed");
  const mgc = page.locator("#pos tr", { hasText: "MGC" });
  assert.match(await mgc.innerText(), /-1/);
  assert.match(await mgc.innerText(), /-3/);
  // qty -1 vs target -3 is a real gap, so the target cell is marked
  assert.equal(await mgc.locator("td.down").count() >= 1, true);
});

await check("trade history renders newest first", async () => {
  const first = await page.locator("#trades tr").first().innerText();
  assert.match(first, /MGC/);
  assert.match(first, /SELL/);
});

await check("markup in a log message is shown as text, not executed", async () => {
  const feed = await txt("#feed");
  assert.ok(feed.includes("<script>alert(1)</script>"),
            "the message must appear literally");
  assert.equal(await page.locator("#feed script").count(), 0);
});

await check("a stale snapshot is called stale", async () => {
  SNAP.generated = Date.now() - 20 * 60e3;
  await page.waitForFunction(() =>
    /stale/.test(document.getElementById("status").textContent),
    null, { timeout: 10000 });
  assert.match(await txt("#meta"), /20m ago/);
  assert.equal(await page.locator("#dot.on").count(), 0,
               "the light must go out when the data is old");
});

await check("the key survives a reload", async () => {
  SNAP.generated = Date.now();
  await page.reload();
  await page.waitForFunction(() =>
    document.getElementById("eq").textContent !== "—", null, { timeout: 8000 });
  assert.equal(await page.locator("#kin").count(), 0);
});

await check("the key can be passed in the URL fragment and is stripped", async () => {
  await ctx.clearCookies();
  const p2 = await ctx.newPage();
  await p2.goto(`${base}/monitor/#k=${READ}`);
  await p2.waitForFunction(() =>
    document.getElementById("eq").textContent !== "—", null, { timeout: 8000 });
  assert.equal(new URL(p2.url()).hash, "", "the key must not stay in the URL");
  await p2.close();
});

await check("no javascript errors anywhere in that run", async () => {
  assert.deepEqual(errors, []);
});

await browser.close();
srv.close();
console.log(failed ? `\n${failed} FAILED` : "\nall page checks passed");
process.exit(failed ? 1 : 0);
