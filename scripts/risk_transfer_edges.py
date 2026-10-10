#!/usr/bin/env python3
"""Slate 2: risk-transfer effects, not price patterns.

Slate 1 (ares/edges.py) tested seven standard price-based factors on the eight
tradeable markets. Only short-horizon cross-sectional reversal had an edge;
every other candidate measured below 0.15 and every one REDUCED the combined
Sharpe. That reframes the search. Reversal is not a prediction, it is a
LIQUIDITY-PROVISION premium -- payment for absorbing someone's urgent order
flow. So the natural second edge is another form of paid risk transfer, not
another pattern in prices.

Two documented candidates, both testable with data already on disk:

  OVERNIGHT EFFECT. Equity index returns accrue almost entirely outside
  regular trading hours. Cooper, Cliff & Gulen; Lou, Polk & Skouras ("A Tug
  of War", 2019). Mechanically it is compensation for holding unhedgeable
  gap risk through a closed market -- a risk transfer, and a time-of-day
  exposure that cannot correlate with a cross-sectional bet by construction.

  TURN OF THE MONTH. Returns concentrate in the window spanning month end.
  Ariel (1987), Lakonishok & Smidt (1988). Usually attributed to the timing
  of institutional flows -- again a flow effect rather than a forecast.

Screened first by raw statistics, which is cheap and decisive, before
anything is built. Both are reported whichever way they come out.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EIGHT_H = ["ES", "NQ", "YM", "GC", "SI", "CL", "6E", "6A"]
# US regular trading hours in UTC, read off the volume profile of the data:
# hours 14-20 UTC carry by far the most volume, i.e. 09:30-16:00 New York.
RTH_OPEN, RTH_CLOSE = 14, 21
TD = 252


def hourly(sym: str) -> pd.Series:
    d = pd.read_csv(f"data/futures_db_1h/{sym}.csv")
    s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
    return s[~s.index.duplicated(keep="last")].sort_index()


def split_sessions(s: pd.Series) -> pd.DataFrame:
    """Per calendar day: the day (RTH) return and the night return.

    night  = last RTH print of the previous day -> first RTH print of today
    day    = first RTH print of today           -> last RTH print of today
    Their compounded product is the close-to-close return, so the two
    partition the day's P&L with nothing double counted.
    """
    rth = s[(s.index.hour >= RTH_OPEN) & (s.index.hour <= RTH_CLOSE)]
    g = rth.groupby(rth.index.normalize())
    first, last = g.first(), g.last()
    day = last / first - 1.0
    night = first / last.shift(1) - 1.0
    out = pd.DataFrame({"day": day, "night": night}).dropna()
    # A gap beyond 25% across a session boundary is a roll, not a return.
    return out[(out.abs() < 0.25).all(axis=1)]


def main() -> int:
    print("=== OVERNIGHT EFFECT: where does the return actually accrue? ===")
    print(f"  RTH taken as {RTH_OPEN}:00-{RTH_CLOSE}:00 UTC "
          f"(peak-volume hours = 09:30-16:00 New York)\n")
    print(f"  {'market':>7} {'days':>6} {'night %/yr':>11} {'t':>6}"
          f" {'day %/yr':>10} {'t':>6} {'night Sharpe':>13}")
    print("  " + "-" * 68)
    frames = {}
    for sym in EIGHT_H:
        f = split_sessions(hourly(sym))
        frames[sym] = f
        out = []
        for col in ("night", "day"):
            r = f[col]
            ann = r.mean() * TD * 100
            t = r.mean() / r.std() * np.sqrt(len(r))
            out.append((ann, t))
        nsh = f["night"].mean() / f["night"].std() * np.sqrt(TD)
        print(f"  {sym:>7} {len(f):6d} {out[0][0]:+10.2f}% {out[0][1]:+6.2f}"
              f" {out[1][0]:+9.2f}% {out[1][1]:+6.2f} {nsh:+13.2f}")

    # The tradeable version: equal-weight long the basket overnight only.
    nights = pd.DataFrame({k: v["night"] for k, v in frames.items()}).dropna()
    days = pd.DataFrame({k: v["day"] for k, v in frames.items()}).dropna()
    bn, bd = nights.mean(axis=1), days.mean(axis=1)
    print(f"\n  equal-weight basket, long overnight only:")
    print(f"    {bn.mean()*TD*100:+.2f}%/yr  Sharpe "
          f"{bn.mean()/bn.std()*np.sqrt(TD):+.2f}  "
          f"t={bn.mean()/bn.std()*np.sqrt(len(bn)):+.2f}  n={len(bn):,}")
    print(f"  same basket, long during the day only:")
    print(f"    {bd.mean()*TD*100:+.2f}%/yr  Sharpe "
          f"{bd.mean()/bd.std()*np.sqrt(TD):+.2f}  "
          f"t={bd.mean()/bd.std()*np.sqrt(len(bd)):+.2f}")
    h = len(bn) // 2
    f = lambda x: x.mean() / x.std() * np.sqrt(TD)
    print(f"  overnight IS {f(bn[:h]):+.2f}  OOS {f(bn[h:]):+.2f}")

    print("\n=== TURN OF THE MONTH ===")
    print("  window = last trading day of the month plus the first three\n")
    px = {}
    for sym in EIGHT_H:
        s = hourly(sym)
        px[sym] = s.resample("1D").last().dropna()
    P = pd.DataFrame(px).dropna()
    r = P.pct_change().dropna()
    basket = r.mean(axis=1)
    # Rank each day within its month from both ends.
    idx = pd.Series(basket.index, index=basket.index)
    from_start = idx.groupby([idx.dt.year, idx.dt.month]).rank(method="first")
    from_end = idx.groupby([idx.dt.year, idx.dt.month]).rank(
        method="first", ascending=False)
    tom = (from_end == 1) | (from_start <= 3)
    a, b = basket[tom], basket[~tom]
    print(f"  {'window':>14} {'days':>7} {'mean bp/day':>12} {'%/yr':>9} {'t':>7}")
    for label, x in (("turn of month", a), ("rest of month", b)):
        print(f"  {label:>14} {len(x):7,} {x.mean()*1e4:+11.2f} "
              f"{x.mean()*TD*100:+8.2f}% {x.mean()/x.std()*np.sqrt(len(x)):+7.2f}")
    print(f"  difference: {(a.mean()-b.mean())*1e4:+.2f} bp/day")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
