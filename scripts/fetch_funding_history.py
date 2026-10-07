#!/usr/bin/env python3
"""Fetch REAL perpetual funding-rate history from Binance's public data vault.

Binance's trading API (fapi) is geo-blocked from cloud IPs (HTTP 451), but
data.binance.vision is not. It serves monthly funding dumps already in the
shape ares.carry.run_carry expects:

    calc_time, funding_interval_hours, last_funding_rate

    python scripts/fetch_funding_history.py ETHUSDT BTCUSDT SOLUSDT
"""
import csv
import io
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
BASE = ("https://data.binance.vision/data/futures/um/monthly/fundingRate/"
        "{sym}/{sym}-fundingRate-{ym}.zip")


def months(start_year: int = 2020):
    today = date.today()
    y, m = start_year, 1
    while (y, m) <= (today.year, today.month):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_symbol(sym: str):
    rows = []
    for ym in months():
        url = BASE.format(sym=sym, ym=ym)
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=45).read()
        except urllib.error.HTTPError:
            continue                      # month not published
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            name = z.namelist()[0]
            text = z.read(name).decode()
        for r in csv.reader(io.StringIO(text)):
            if not r or r[0].startswith("calc_time"):
                continue
            try:
                rows.append((int(r[0]), float(r[1]), float(r[2])))
            except (ValueError, IndexError):
                continue
    rows.sort(key=lambda x: x[0])
    return rows


def main() -> int:
    syms = sys.argv[1:] or ["ETHUSDT", "BTCUSDT", "SOLUSDT"]
    Path("data/funding").mkdir(parents=True, exist_ok=True)
    for s in syms:
        rows = fetch_symbol(s)
        if not rows:
            print(f"  {s:10s} no data", file=sys.stderr)
            continue
        out = Path("data/funding") / f"{s}.csv"
        with out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["calc_time", "funding_interval_hours", "last_funding_rate"])
            w.writerows(rows)
        yrs = (rows[-1][0] - rows[0][0]) / 86_400_000 / 365.25
        ann = sum(r[2] for r in rows) / yrs * 100
        print(f"  {s:10s} {len(rows):6d} intervals  {yrs:4.1f}yr  "
              f"mean rate {sum(r[2] for r in rows)/len(rows)*1e4:6.2f}bp/8h  "
              f"=> gross carry {ann:6.1f}%/yr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
