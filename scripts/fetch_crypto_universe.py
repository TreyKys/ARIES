#!/usr/bin/env python3
"""Fetch a wide crypto universe for FAST (high-bet-count) strategy research.

Rationale: strategy quality = (edge per bet) * sqrt(bets per year). Trend
following makes ~25 bets/yr, so sqrt(25)=5 caps its quality near 0.5 no matter
how well it is tuned. A strategy rebalancing hourly across a wide universe
makes thousands of bets, so sqrt(N) is ~100 and a far smaller per-bet edge
reaches the quality needed to earn inside a tight drawdown limit.

Costs scale with bet count too, so the per-bet edge must clear its own fees --
that is the thing to measure, not assume.
"""
import csv, io, sys, urllib.request, zipfile
from pathlib import Path

UA = {"User-Agent": "curl/8"}
PAIRS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT",
         "AVAXUSDT","DOTUSDT","LINKUSDT","MATICUSDT","LTCUSDT","ATOMUSDT",
         "UNIUSDT","ETCUSDT","XLMUSDT","NEARUSDT","FILUSDT","AAVEUSDT",
         "ALGOUSDT","VETUSDT","ICPUSDT","SANDUSDT","EOSUSDT","THETAUSDT"]


def months(y0, m0, y1, m1):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch(sym, tf, y0=2021):
    import datetime as dt
    t = dt.date.today()
    rows = []
    for ym in months(y0, 1, t.year, t.month):
        url = (f"https://data.binance.vision/data/spot/monthly/klines/"
               f"{sym}/{tf}/{sym}-{tf}-{ym}.zip")
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                         timeout=40).read()
        except Exception:
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for line in z.read(z.namelist()[0]).decode().splitlines():
                p = line.split(",")
                if p[0].lower().startswith("open"):
                    continue
                ts = int(float(p[0]))
                if ts > 1e14:
                    ts //= 1000
                rows.append((ts, float(p[4]), float(p[5])))
    rows.sort()
    return rows


def main() -> int:
    tf = sys.argv[1] if len(sys.argv) > 1 else "1h"
    out = Path(f"data/crypto_{tf}"); out.mkdir(parents=True, exist_ok=True)
    ok = 0
    for s in PAIRS:
        rows = fetch(s, tf)
        if len(rows) < 2000:
            print(f"  {s:12s} skip ({len(rows)})", file=sys.stderr); continue
        with (out / f"{s}.csv").open("w", newline="") as f:
            w = csv.writer(f); w.writerow(["ts","close","volume"]); w.writerows(rows)
        print(f"  {s:12s} {len(rows):7d} bars "
              f"{(rows[-1][0]-rows[0][0])/86400000/365.25:4.1f}yr")
        ok += 1
    print(f"{ok}/{len(PAIRS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
