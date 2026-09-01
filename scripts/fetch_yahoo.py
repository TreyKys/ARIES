#!/usr/bin/env python3
"""Fetch OHLCV from Yahoo Finance (works for FX majors, indices, metals).

Writes data/{NAME}_{interval}.csv with headers ts,open,high,low,close,volume.

Usage: python scripts/fetch_yahoo.py EURUSD=X EURUSD 1h 730d
"""
import csv
import json
import os
import sys
import urllib.request


def fetch(symbol: str, interval: str, rng: str):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&range={rng}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=40).read())
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        v = q.get("volume", [0] * len(ts))[i] or 0
        rows.append((int(t) * 1000, o, h, l, c, v))
    return rows


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSD=X"
    name = sys.argv[2] if len(sys.argv) > 2 else "EURUSD"
    interval = sys.argv[3] if len(sys.argv) > 3 else "1h"
    rng = sys.argv[4] if len(sys.argv) > 4 else "730d"
    rows = fetch(symbol, interval, rng)
    if not rows:
        print(f"No data for {symbol}", file=sys.stderr); return 1
    rows.sort(key=lambda r: r[0])
    os.makedirs("data", exist_ok=True)
    out = f"data/{name}_{interval}.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ts", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    days = (rows[-1][0] - rows[0][0]) / 86_400_000
    print(f"Wrote {out}: {len(rows)} candles over {days:.0f} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
