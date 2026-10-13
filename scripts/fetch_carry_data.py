#!/usr/bin/env python3
"""Fetch front- and second-month DAILY futures bars for a carry signal.

Carry is the one classic factor this repo could not test: it needs the slope
of each market's futures curve, i.e. at least two contract months per market,
and only crude and natural gas were on disk. It is also the natural answer to
the fee problem. The one-day reversal edge must rebuild the book every day
and Phidias's per-contract commission eats most of it; carry is rebalanced
monthly, so its fee bill is a rounding error.

Databento continuous symbology: ROOT.c.0 is the front contract by calendar,
ROOT.c.1 the next. map_symbols adds the raw contract code (e.g. ESZ5) so the
expiry month -- and therefore the time between the two contracts, which carry
is annualised over -- is known exactly rather than assumed.

Quote before purchase (metadata.get_cost, free): $1.30 for 14 roots,
2010-06 to 2026-10. Key read from the environment, never from source.
"""
import base64
import csv
import io
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KEY = os.environ.get("DATABENTO_API_KEY", "").strip()
URL = "https://hist.databento.com/v0/timeseries.get_range"
ROOTS = ["ES", "NQ", "YM", "RTY", "GC", "SI", "HG", "CL",
         "6E", "6A", "6B", "6J", "ZN", "ZB"]
OUT = Path("data/carry")
PRICE_SCALE = 1e9


def main() -> int:
    if not KEY:
        print("DATABENTO_API_KEY not set", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    params = {
        "dataset": "GLBX.MDP3",
        "symbols": ",".join(f"{r}.c.{i}" for r in ROOTS for i in (0, 1)),
        "schema": "ohlcv-1d", "stype_in": "continuous", "encoding": "csv",
        "map_symbols": "true", "start": "2010-06-07", "end": "2026-10-10",
    }
    req = urllib.request.Request(
        f"{URL}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": "Basic "
                 + base64.b64encode(f"{KEY}:".encode()).decode()})
    raw = urllib.request.urlopen(req, timeout=900).read().decode()
    rows = list(csv.DictReader(io.StringIO(raw)))
    print(f"received {len(rows):,} rows; columns: {list(rows[0])}")
    by = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(r)
    for sym, rs in sorted(by.items()):
        # continuous symbol such as ES.c.0 -> file ES_c0.csv
        name = sym.replace(".", "_").replace("_c_", "_c")
        with (OUT / f"{name}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "close", "volume", "contract"])
            for r in rs:
                px = float(r["close"])
                if px > 1e6:                       # fixed-point price
                    px /= PRICE_SCALE
                w.writerow([r["ts_event"][:10], px, r["volume"],
                            r.get("instrument_id", "")])
        print(f"  {sym:8s} {len(rs):5d} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
