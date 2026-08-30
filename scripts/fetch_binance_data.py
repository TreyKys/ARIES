#!/usr/bin/env python3
"""Download real historical klines from data.binance.vision (no API key,
not geo-blocked like the trading API) and write a normalized CSV with
headers: ts,open,high,low,close,volume  (ts in epoch ms).

Usage:
    python scripts/fetch_binance_data.py BTCUSDT 5m 2024-01 2025-06 spot
"""
import io
import sys
import csv
import zipfile
import urllib.request
from datetime import date


def month_range(start: str, end: str):
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    tf = sys.argv[2] if len(sys.argv) > 2 else "5m"
    start = sys.argv[3] if len(sys.argv) > 3 else "2024-01"
    end = sys.argv[4] if len(sys.argv) > 4 else "2024-12"
    market = sys.argv[5] if len(sys.argv) > 5 else "spot"  # spot | futures

    base = ("https://data.binance.vision/data/spot/monthly/klines"
            if market == "spot" else
            "https://data.binance.vision/data/futures/um/monthly/klines")

    rows = []
    for ym in month_range(start, end):
        url = f"{base}/{symbol}/{tf}/{symbol}-{tf}-{ym}.zip"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  skip {ym}: {type(e).__name__}", file=sys.stderr)
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = z.namelist()[0]
            for line in z.read(name).decode().splitlines():
                p = line.split(",")
                if p[0].lower().startswith("open"):   # header row in newer files
                    continue
                ts = int(float(p[0]))
                if ts > 1e14:          # microseconds -> ms
                    ts //= 1000
                rows.append((ts, p[1], p[2], p[3], p[4], p[5]))
        print(f"  got {ym}  ({len(rows)} rows total)", file=sys.stderr)

    if not rows:
        print("No data downloaded.", file=sys.stderr)
        return 1
    rows.sort(key=lambda x: x[0])

    out = f"data/{symbol}_{tf}.csv"
    import os
    os.makedirs("data", exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    span_days = (rows[-1][0] - rows[0][0]) / 86_400_000
    print(f"Wrote {out}: {len(rows)} candles over {span_days:.0f} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
