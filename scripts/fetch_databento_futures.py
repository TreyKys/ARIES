#!/usr/bin/env python3
"""Pull 16 years of HOURLY CME futures bars from Databento.

Why: the cross-sectional reversal edge is confirmed at DAILY frequency over 57
years (Sharpe 0.49 after costs, t=3.50), and the HOURLY version looked far
better (Sharpe 1.80 out-of-sample) but rested on only 1.2 years, giving a
standard error of +/-1.48 and t=1.22 -- promising, unproven. Sharpe error scales
with elapsed YEARS, so 16 years takes the error to roughly +/-0.25 and settles
it.

Databento serves CME ohlcv-1h from 2010-06-06. Cost for 20 continuous contracts
over 10 years quoted at $8.85, well inside the $125 signup credit.

Notes on the format: ts_event is nanoseconds, prices are integers scaled by
1e9, and `map_symbols=true` adds the symbol column so one request can cover the
whole universe per year.

    DATABENTO_API_KEY=... python scripts/fetch_databento_futures.py
"""
import csv
import io
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

KEY = os.environ.get("DATABENTO_API_KEY", "").strip()
URL = "https://hist.databento.com/v0/timeseries.get_range"
SYMBOLS = ["ES", "NQ", "YM", "RTY", "GC", "SI", "HG", "PL", "CL", "NG",
           "RB", "HO", "ZN", "ZB", "ZF", "6E", "6J", "6B", "6A", "ZC"]
PRICE_SCALE = 1e9
OUT = Path("data/futures_db_1h")


def fetch_year(year: int):
    """One request covering every symbol for one calendar year."""
    params = {
        "dataset": "GLBX.MDP3",
        "symbols": ",".join(f"{s}.c.0" for s in SYMBOLS),
        "schema": "ohlcv-1h",
        "stype_in": "continuous",
        "encoding": "csv",
        "map_symbols": "true",
        "start": f"{year}-01-01",
        "end": f"{year + 1}-01-01",
    }
    req = urllib.request.Request(
        f"{URL}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": "Basic " + __import__("base64")
                 .b64encode(f"{KEY}:".encode()).decode()})
    return urllib.request.urlopen(req, timeout=600).read().decode()


def main() -> int:
    if not KEY:
        print("DATABENTO_API_KEY not set", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    rows_by_sym = defaultdict(list)
    for year in range(2010, 2027):
        try:
            text = fetch_year(year)
        except Exception as e:  # noqa: BLE001
            print(f"  {year}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
            continue
        n = 0
        for rec in csv.DictReader(io.StringIO(text)):
            sym = (rec.get("symbol") or "").split(".")[0]
            if not sym:
                continue
            try:
                ts_ms = int(rec["ts_event"]) // 1_000_000
                close = float(rec["close"]) / PRICE_SCALE
                vol = float(rec.get("volume") or 0)
            except (ValueError, KeyError):
                continue
            if close <= 0:
                continue
            rows_by_sym[sym].append((ts_ms, close, vol))
            n += 1
        print(f"  {year}: {n:,} bars", flush=True)

    total = 0
    for sym, rows in sorted(rows_by_sym.items()):
        rows.sort()
        # de-duplicate on timestamp, keeping the last print
        dedup = {}
        for ts, c, v in rows:
            dedup[ts] = (c, v)
        with (OUT / f"{sym}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "close", "volume"])
            for ts in sorted(dedup):
                c, v = dedup[ts]
                w.writerow([ts, c, v])
        yrs = (max(dedup) - min(dedup)) / 86_400_000 / 365.25 if dedup else 0
        print(f"  {sym:5s} {len(dedup):7,} bars  {yrs:5.1f}yr")
        total += len(dedup)
    print(f"{len(rows_by_sym)} symbols, {total:,} bars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
