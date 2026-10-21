#!/usr/bin/env python3
"""The reversal book on FX majors alone -- the configuration with no swap.

The venue work (docs/FEES_AND_VENUE.md) found that the deciding unknown at a
CFD prop firm is the overnight swap, charged on every position every night,
and this book holds everything overnight. FundedNext offers swap-free
accounts on every challenge with no paperwork, but confirms swap-free only
for "all major Forex pairs". So a book that trades ONLY the FX majors removes
the unknown entirely -- and FX was already where the overnight edge was
strongest (6E and 6A were the top overnight earners in the session split).

Construction:
  * the seven majors, all expressed as the dollar value of the currency
    (EUR, GBP, AUD, NZD as quoted; CAD, CHF, JPY inverted). Mixing the two
    quoting conventions would turn the cross-sectional ranking into a bet on
    the dollar, because a dollar move pushes the two groups in opposite
    directions and demeaning no longer removes it.
  * one-day cross-sectional reversal, inverse-volatility weights, the same
    rule as the futures book; top_k by the universe-size rule fixed earlier
    (max(3, N//3) = 3), with k=2 shown only as a robustness check.
  * all seven come from one data source on one clock, so no pair is stale
    relative to another -- the non-synchronous-close problem cannot arise.
  * costs: CFD spread plus commission per side, estimated; shown at three
    levels because FundedNext's exact spreads are not public.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TD = 252
QUOTED = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
INVERT = {"USDCAD": "CAD", "USDCHF": "CHF", "USDJPY": "JPY"}


def load(folder="data/daily") -> pd.DataFrame:
    cols = {}
    for f in QUOTED + list(INVERT):
        d = pd.read_csv(f"{folder}/{f}.csv")
        # Yahoo stamps some FX days at 23:00 UTC and others at 00:00 UTC.
        # Taking the date naively would put the same session on two
        # different days for different pairs. Shift two hours first.
        idx = (pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms"))
               + pd.Timedelta(hours=2)).normalize()
        s = pd.Series(d["close"].values, index=idx)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        s = s[s > 0]
        name = INVERT.get(f, f[:3])
        cols[name] = (1.0 / s) if f in INVERT else s
    P = pd.DataFrame(cols).sort_index()
    P = P[P.index.dayofweek < 5].dropna(thresh=6).ffill()
    return P.iloc[:-1]            # drop a possibly partial final bar


def weights(P, k=3):
    r = P.pct_change().where(lambda x: x.abs() < 0.08)
    vol = r.rolling(60, min_periods=30).std()
    W = pd.DataFrame(0.0, index=P.index, columns=P.columns)
    for t in range(61, len(P)):
        x = r.iloc[t].dropna()
        if len(x) < 6:
            continue
        x = x - x.mean()
        o = x.sort_values().index
        w = pd.Series(0.0, index=P.columns)
        w[o[:k]], w[o[-k:]] = 1.0, -1.0
        w = (w / vol.iloc[t].where(vol.iloc[t] > 0)).fillna(0.0)
        g = w.abs().sum()
        W.iloc[t] = w / g if g else 0.0
    return W, r


def evaluate(W, r, side_bp):
    gross = (W.shift(1) * r).sum(axis=1)
    turn = (W - W.shift(1)).abs().sum(axis=1)
    live = W.shift(1).abs().sum(axis=1) > 0
    net = gross - turn * side_bp / 1e4
    return gross[live], net[live], turn[live]


def sh(x):
    return float(x.mean() / x.std() * np.sqrt(TD)) if x.std() else 0.0


def main() -> int:
    P = load()
    print(f"\nFX majors, {P.index[0].date()} -> {P.index[-1].date()} "
          f"({(P.index[-1]-P.index[0]).days/365.25:.1f}yr), {', '.join(P.columns)}")
    print("correlation of daily moves AFTER removing the dollar factor:")
    r = P.pct_change()
    dm = r.sub(r.mean(axis=1), axis=0)
    c = dm.corr().where(~np.eye(len(P.columns), dtype=bool))
    print(f"  mean pairwise {c.stack().mean():+.2f}, range "
          f"{c.stack().min():+.2f} to {c.stack().max():+.2f}")

    for k in (3, 2):
        W, rr = weights(P, k)
        g, _, t = evaluate(W, rr, 0.0)
        h = len(g) // 2
        tag = "pre-committed rule" if k == 3 else "robustness check only"
        print(f"\n--- top_k={k} ({tag}) ---")
        print(f"  gross Sharpe {sh(g):+.2f}  t={g.mean()/g.std()*np.sqrt(len(g)):+.2f}"
              f"  IS {sh(g.iloc[:h]):+.2f}  OOS {sh(g.iloc[h:]):+.2f}"
              f"  gross {g.mean()*TD*100:+.2f}%/yr at 1x  turnover {t.mean():.2f}x/day")
        be = g.mean() / t.mean() * 1e4
        print(f"  breakeven cost per side: {be:.2f}bp")
        for bp in (0.3, 0.5, 0.8):
            _, n, _ = evaluate(W, rr, bp)
            print(f"  net @ {bp:.1f}bp/side, no swap: Sharpe {sh(n):+.2f}"
                  f"  (IS {sh(n.iloc[:h]):+.2f} / OOS {sh(n.iloc[h:]):+.2f})"
                  f"  {n.mean()*TD*100:+.2f}%/yr")
        if k == 3:
            print("  by period (gross Sharpe):")
            for y in range(2004, 2027, 4):
                m = (g.index.year >= y) & (g.index.year <= y + 3)
                if m.sum() > 200:
                    print(f"    {y}-{min(y+3, 2026)}  {sh(g[m]):+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
