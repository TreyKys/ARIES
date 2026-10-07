#!/usr/bin/env python3
"""Fetch MAXIMUM daily history from Yahoo for a diversified futures-style basket.

Why daily and why maximum: the standard error of a Sharpe ratio depends on
elapsed YEARS, not on the number of bars. A year of 15-minute candles is no more
informative about whether an edge exists than a year of daily candles. Only
decades buy statistical power, so this fetches from epoch 0.

NOTE: `range=max` silently downgrades the interval (it returned 169 rows for 42
years of ^GSPC). Explicit period1/period2 is required to get true daily bars.
"""
import csv
import json
import os
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

BASKET = {
    # equity indices
    "^GSPC": "SPX", "^IXIC": "NDX", "^DJI": "DJI", "^N225": "NKY",
    "^GDAXI": "DAX", "^FTSE": "UKX", "^HSI": "HSI", "^AXJO": "AS51",
    # FX (vs USD)
    "EURUSD=X": "EURUSD", "JPY=X": "USDJPY", "GBPUSD=X": "GBPUSD",
    "AUDUSD=X": "AUDUSD", "CAD=X": "USDCAD", "CHF=X": "USDCHF",
    # commodities
    "GC=F": "GOLD", "SI=F": "SILVER", "CL=F": "WTI", "NG=F": "NATGAS",
    "HG=F": "COPPER", "ZC=F": "CORN", "ZS=F": "SOY", "ZW=F": "WHEAT",
    # rates / bonds
    "^TNX": "US10Y", "ZN=F": "UST10", "ZB=F": "UST30",
    # --- breadth extension ---------------------------------------------------
    # A real CTA runs 50-100+ markets. Added uncorrelated markets are pure
    # diversification, the one improvement that is not a fitted parameter:
    # portfolio Sharpe scales with sqrt(number of independent bets.)
    "^FCHI": "CAC", "^STOXX50E": "SX5E", "^KS11": "KOSPI", "^TWII": "TWSE",
    "^BSESN": "SENSEX", "^BVSP": "BOVESPA", "^MXX": "IPC", "^SSMI": "SMI",
    "^AEX": "AEX", "^IBEX": "IBEX", "^OMX": "OMX", "^GSPTSE": "TSX",
    "NZDUSD=X": "NZDUSD", "EURGBP=X": "EURGBP", "EURJPY=X": "EURJPY",
    "GBPJPY=X": "GBPJPY", "AUDJPY=X": "AUDJPY", "SEK=X": "USDSEK",
    "NOK=X": "USDNOK", "MXN=X": "USDMXN", "ZAR=X": "USDZAR",
    "PL=F": "PLATINUM", "PA=F": "PALLADIUM", "CC=F": "COCOA", "KC=F": "COFFEE",
    "SB=F": "SUGAR", "CT=F": "COTTON", "LE=F": "CATTLE", "HE=F": "HOGS",
    "RB=F": "GASOLINE", "HO=F": "HEATOIL", "ZM=F": "SOYMEAL", "ZL=F": "SOYOIL",
    "^FVX": "US5Y", "^TYX": "US30Y",
}


def fetch(symbol: str):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?period1=0&period2={int(time.time())}"
           f"&interval=1d")
    req = urllib.request.Request(url, headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    res = d["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        rows.append((int(t) * 1000, o, h, l, c, (q.get("volume") or [0]*len(ts))[i] or 0))
    return rows


def main() -> int:
    os.makedirs("data/daily", exist_ok=True)
    ok = 0
    for sym, name in BASKET.items():
        try:
            rows = fetch(sym)
        except Exception as e:  # noqa: BLE001
            print(f"  {name:8s} FAILED {type(e).__name__}", file=sys.stderr)
            continue
        if len(rows) < 500:
            print(f"  {name:8s} too short ({len(rows)})", file=sys.stderr)
            continue
        rows.sort(key=lambda r: r[0])
        with open(f"data/daily/{name}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "open", "high", "low", "close", "volume"])
            w.writerows(rows)
        yrs = (rows[-1][0]-rows[0][0])/86_400_000/365.25
        print(f"  {name:8s} {len(rows):6d} rows  {yrs:5.1f}yr")
        ok += 1
        time.sleep(1.2)
    print(f"{ok}/{len(BASKET)} fetched")
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
