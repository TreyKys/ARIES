#!/usr/bin/env python3
"""Does the reversal edge depend on WHAT TIME OF DAY you call 'the close'?

On Yahoo daily data the reversal book scored 0.54-0.94. On synchronised hourly
session closes (16:00 New York) it scored 0.67 gross. On Databento's own daily
futures bars it scores 0.00. Databento's daily bars are UTC-day bars, so their
'close' is the last trade before midnight UTC -- 20:00 New York, four hours
after the cash session ends.

A real, robust reversal effect should survive moving the measurement point by
a few hours. An edge that exists only at one particular clock time is a
microstructure effect at that time -- closing-auction pressure, or a stale
price somewhere in the panel -- and is far more fragile than a daily Sharpe
suggests. This measures the same book with 'the close' set to each hour of
the UTC day, on synchronised hourly prices, so no market is ever stale
relative to another.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EIGHT = ["ES", "NQ", "YM", "GC", "SI", "CL", "6E", "6A"]
TD = 252


def hourly(sym):
    d = pd.read_csv(f"data/futures_db_1h/{sym}.csv")
    s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
    return s[~s.index.duplicated(keep="last")].sort_index()


_GRID = {}


def at_hour(H):
    """Each market's last price AT OR BEFORE HH:00 UTC, one row per day.

    Requiring a bar at exactly that hour from all eight markets at once threw
    away most days (242 survived at 16:00 NY, 46 at 17:00) and made every
    figure meaningless. Instead each market is carried forward on an hourly
    grid -- for at most 3 hours, so a dead market is never treated as live --
    and sampled at the hour.
    """
    cols = {}
    for m in EIGHT:
        if m not in _GRID:
            s = hourly(m)
            grid = pd.date_range(s.index[0].floor("h"), s.index[-1].ceil("h"),
                                 freq="h")
            _GRID[m] = s.reindex(grid).ffill(limit=3)
        g = _GRID[m]
        g = g[g.index.hour == H]
        # weekends: drop days where nothing traded in the preceding hours
        cols[m] = g[g.index.dayofweek < 5]
    P = pd.DataFrame(cols)
    P.index = P.index.normalize()
    return P.dropna(thresh=6)


def book(P, k=3):
    r = P.pct_change().where(lambda x: x.abs() < 0.15)
    vol = r.rolling(60, min_periods=30).std()
    W = pd.DataFrame(0.0, index=P.index, columns=P.columns)
    for t in range(61, len(P)):
        x = r.iloc[t].dropna()
        if len(x) < 6:
            continue
        x = x - x.mean()
        o = x.sort_values().index
        w = pd.Series(0.0, index=P.columns)
        w[o[:k]] = 1.0
        w[o[-k:]] = -1.0
        w = (w / vol.iloc[t].where(vol.iloc[t] > 0)).fillna(0.0)
        g = w.abs().sum()
        W.iloc[t] = w / g if g else 0.0
    p = (W.shift(1) * r).sum(axis=1)
    return p[W.shift(1).abs().sum(axis=1) > 0]


def main() -> int:
    print("\nSame reversal book, 'close' set to each UTC hour (gross of costs)")
    print("New York = UTC-4 in summer, UTC-5 in winter\n")
    print(f"  {'close at':>9} {'~New York':>10} {'days':>6} {'Sharpe':>8} {'t':>7}  ")
    for H in (13, 15, 17, 19, 20, 21, 22, 23, 0, 2, 4, 7, 10):
        p = book(at_hour(H))
        s = p.mean() / p.std() * np.sqrt(TD)
        t = p.mean() / p.std() * np.sqrt(len(p))
        ny = (H - 4) % 24
        bar = "#" * max(0, int(round(s * 20))) if s > 0 else "-" * int(round(-s * 20))
        note = ""
        if H == 20:
            note = "  <- cash session close"
        if H == 0:
            note = "  <- Databento daily bar close"
        print(f"  {H:02d}:00 UTC {ny:02d}:00 NY {len(p):6d} {s:+8.2f} {t:+7.2f}  {bar}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
