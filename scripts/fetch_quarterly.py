#!/usr/bin/env python3
"""Fetch Binance QUARTERLY (dated) futures klines and stitch per-contract files.

Why: a dated future pays no funding, a perp does. Long dated + short perp is
therefore delta-neutral AND funding-collecting with BOTH legs as derivatives in
ONE account -- no spot, so it fits a prop account. The cost is the dated
contract's own premium decaying to spot by expiry, so the real edge is the
SPREAD between perp funding and dated basis. This fetches the data to measure it.
"""
import csv, io, sys, urllib.request, zipfile
from pathlib import Path

UA = {"User-Agent": "curl/8"}
EXPIRIES = [f"{y}{md}" for y in range(21, 27)
            for md in ("0326", "0625", "0924", "1231", "0325", "0624", "0930",
                       "1230", "0331", "0630", "0929", "1229", "0329", "0628",
                       "0927", "1227", "0328", "0627", "0926", "1226", "0327",
                       "0626")]


def months_for(expiry, lookback=10):
    """Only the months a dated contract actually traded.

    Scanning every month for every contract is ~1800 requests and takes far too
    long; a quarterly lists roughly 9 months before expiry, so fetch that window.
    """
    y, m = 2000 + int(expiry[:2]), int(expiry[2:4])
    out = []
    for back in range(lookback, -1, -1):
        yy, mm = y, m - back
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def fetch(sym, tf="1h"):
    rows = []
    expiry = sym.split("_")[1]
    for ym in months_for(expiry):
        url = (f"https://data.binance.vision/data/futures/um/monthly/klines/"
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
                rows.append((ts, float(p[4])))
    rows.sort()
    return rows


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    out = Path("data/quarterly"); out.mkdir(parents=True, exist_ok=True)
    got = 0
    for e in dict.fromkeys(EXPIRIES):
        sym = f"{base}_{e}"
        rows = fetch(sym)
        if len(rows) < 200:
            continue
        with (out / f"{sym}.csv").open("w", newline="") as f:
            w = csv.writer(f); w.writerow(["ts", "close"]); w.writerows(rows)
        days = (rows[-1][0] - rows[0][0]) / 86_400_000
        print(f"  {sym}: {len(rows)} hrs, {days:.0f}d")
        got += 1
    print(f"{got} contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
