#!/usr/bin/env python3
"""Sweep cross-sectional reversal: find where per-bet edge clears per-bet cost.

The decisive metric is BREAKEVEN COST -- the round-trip cost at which the gross
edge is exactly consumed. Compare it against what you can actually trade at:
Binance spot taker ~5bp (10bp round trip), maker ~1bp (2bp round trip), VIP
maker can be ~0. If breakeven sits below the achievable cost, the edge is real
but untradeable, which is the usual fate of fast strategies.

Turnover is the reason: hourly full repositioning trades ~13,500x capital a
year, so a 2bp fee costs ~270%/yr. Longer holds cut the fee bill but also cut
sqrt(bets), so the optimum is a trade-off rather than "as fast as possible".
"""
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from ares.ledger import summarise
from ares.xsreversal import breakeven_cost_bps, run_xs_reversal

TF = sys.argv[1] if len(sys.argv) > 1 else "1h"
BARS_YR = {"1h": 24 * 365, "15m": 96 * 365, "5m": 288 * 365}[TF]


def panel(folder):
    cols = {}
    for p in sorted(glob.glob(f"{folder}/*.csv")):
        name = os.path.basename(p)[:-4]
        d = pd.read_csv(p)
        s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
        cols[name] = s[~s.index.duplicated(keep="last")]
    return pd.DataFrame(cols).sort_index()


def main() -> int:
    px = panel(f"data/crypto_{TF}")
    px = px.dropna(axis=0, thresh=max(8, int(len(px.columns) * 0.6)))
    yrs = (px.index[-1] - px.index[0]).days / 365.25
    print(f"{len(px.columns)} assets, {len(px)} bars, {yrs:.1f}yr\n")

    print(f"{'look':>5s}{'hold':>6s}{'k':>4s}{'gross %/yr':>12s}"
          f"{'turn/reb':>10s}{'bets/yr':>9s}{'BREAKEVEN bp':>14s}{'net@2bp':>10s}")
    print('-' * 70)
    rows = []
    for look in (1, 4, 12, 24):
        for hold in (1, 4, 12, 24, 72):
            for k in (3, 5):
                if hold < look and hold != 1:
                    continue
                kw = dict(lookback=look, hold=hold, top_k=k,
                          bars_per_year=BARS_YR, capital=10_000.0)
                r0 = run_xs_reversal(px, cost_bps=0.0, **kw)
                be = breakeven_cost_bps(px, **kw)
                r2 = run_xs_reversal(px, cost_bps=2.0, **kw)
                s2 = summarise(r2.ledger, periods_per_year=BARS_YR)
                rows.append((be, look, hold, k, r0.gross_return_pct, s2.ann_return_pct))
                print(f"{look:>5d}{hold:>6d}{k:>4d}{r0.gross_return_pct:+11.1f}%"
                      f"{r0.turnover_per_rebalance*100:9.0f}%{r0.bets_per_year:9,.0f}"
                      f"{be:13.2f}{s2.ann_return_pct:+9.1f}%")
    rows.sort(reverse=True)
    print("\nbest by breakeven cost (the only metric that decides tradeability):")
    for be, look, hold, k, g, n in rows[:5]:
        verdict = ("TRADEABLE at maker" if be > 2 else
                   "maker-rebate only" if be > 0.5 else "untradeable")
        print(f"  look={look:2d} hold={hold:2d} k={k}  breakeven {be:6.2f}bp  "
              f"gross {g:+7.1f}%/yr  net@2bp {n:+7.1f}%/yr   -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
