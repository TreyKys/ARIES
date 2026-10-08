#!/usr/bin/env python3
"""Fetch HOURLY futures history for the fast cross-sectional reversal test.

Why futures and not crypto spot: the reversal edge measured on 25 crypto pairs
is real (gross +74.8%/yr at a 4-hour hold) but its breakeven cost is 1.65bp
round-trip, against ~15bp for retail Binance spot. The edge is roughly 10x too
small for those fees, and selectivity does not rescue it -- demanding bigger
dislocations turns the edge NEGATIVE by 2 sigma, because large crypto moves are
news (hacks, listings, liquidation cascades) and news does not revert.

Futures invert the cost side: a couple of dollars commission plus one tick on a
$30,000-44,000 contract is 0.34-0.75bp round-trip, 20-40x cheaper. A 1.65bp
breakeven fails at 15bp and clears at 0.75bp. These are also exactly the
instruments a futures prop firm offers.

Yahoo serves ~730 days of hourly data for these symbols (verified), which is
~2 years: enough for a first read, not enough to pin a Sharpe (standard error
on Sharpe scales with elapsed years, ~0.7 at 2yr).
"""
import csv, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
# A prop futures account's liquid universe, grouped so the cross-section has
# several correlated clusters for the common factor to be stripped out of.
UNIVERSE = {
    "ES=F": "ES", "NQ=F": "NQ", "YM=F": "YM", "RTY=F": "RTY",      # equity index
    "GC=F": "GC", "SI=F": "SI", "HG=F": "HG", "PL=F": "PL",        # metals
    "CL=F": "CL", "NG=F": "NG", "RB=F": "RB", "HO=F": "HO",        # energy
    "ZN=F": "ZN", "ZB=F": "ZB", "ZF=F": "ZF",                      # rates
    "6E=F": "6E", "6J=F": "6J", "6B=F": "6B", "6A=F": "6A",        # FX
    "ZC=F": "ZC", "ZS=F": "ZS", "ZW=F": "ZW",                      # grains
}


def fetch(sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?interval=1h&range=730d")
    d = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=60).read())
    res = d["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        vols = q.get("volume") or [0] * len(ts)
        out.append((int(t) * 1000, float(c), float(vols[i] or 0)))
    return out


def main() -> int:
    out = Path("data/futures_1h"); out.mkdir(parents=True, exist_ok=True)
    ok = 0
    for sym, name in UNIVERSE.items():
        try:
            rows = fetch(sym)
        except Exception as e:  # noqa: BLE001
            print(f"  {name:5s} FAILED {type(e).__name__}", file=sys.stderr); continue
        if len(rows) < 2000:
            print(f"  {name:5s} too short ({len(rows)})", file=sys.stderr); continue
        rows.sort()
        with (out / f"{name}.csv").open("w", newline="") as f:
            w = csv.writer(f); w.writerow(["ts", "close", "volume"]); w.writerows(rows)
        print(f"  {name:5s} {len(rows):6d} bars "
              f"{(rows[-1][0]-rows[0][0])/86400000/365.25:4.1f}yr")
        ok += 1
        time.sleep(1.2)
    print(f"{ok}/{len(UNIVERSE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
