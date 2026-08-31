#!/usr/bin/env python3
"""Download real perpetual funding-rate history from data.binance.vision
and write CSV with headers: ts,interval_hours,rate

Usage: python scripts/fetch_funding.py BTCUSDT 2024-01 2025-06
"""
import io
import os
import sys
import csv
import zipfile
import urllib.request


def month_range(start, end):
    sy, sm = map(int, start.split("-")); ey, em = map(int, end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1; y += 1


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2025-06"
    base = "https://data.binance.vision/data/futures/um/monthly/fundingRate"

    rows = []
    for ym in month_range(start, end):
        url = f"{base}/{symbol}/{symbol}-fundingRate-{ym}.zip"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:  # noqa: BLE001
            print(f"  skip {ym}: {type(e).__name__}", file=sys.stderr); continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for line in z.read(z.namelist()[0]).decode().splitlines():
                p = line.split(",")
                if p[0].lower().startswith("calc"):
                    continue
                ts = int(float(p[0]))
                hrs = float(p[1]) if len(p) > 2 else 8.0
                rate = float(p[-1])
                rows.append((ts, hrs, rate))
    if not rows:
        print("No funding data.", file=sys.stderr); return 1
    rows.sort(key=lambda x: x[0])
    os.makedirs("data", exist_ok=True)
    out = f"data/{symbol}_funding.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ts", "interval_hours", "rate"]); w.writerows(rows)
    print(f"Wrote {out}: {len(rows)} funding intervals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
