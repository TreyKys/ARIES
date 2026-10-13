#!/usr/bin/env python3
"""Cut the reversal book's turnover without cutting its edge.

The fee decomposition (scripts/fee_decomposition.py) found fees eating ~59% of
gross at Phidias's real per-contract prices, and the session split found the
book turning over 1.32x its entire gross exposure EVERY DAY. The commission
rate is not the problem; trading the whole book daily is.

Two standard remedies, both measured here rather than assumed:

  OVERLAPPING PORTFOLIOS. Hold each day's signal for N days with 1/N of the
  capital. Today's trade is only the difference between the newest and the
  oldest slice, so turnover falls roughly N-fold. Worth it only if the signal
  is still paying on days 2..N -- hence the decay profile first.

  PARTIAL ADJUSTMENT. Move only a fraction lambda of the way from today's
  position to today's target. Garleanu & Pedersen (2013): with costs, the
  optimal policy trades partially toward the aim portfolio. Lambda=1 is the
  current book.

Costs are per-contract, from Phidias's schedule (ares/costs.py), expressed in
bp of notional per market. Everything is computed on a gross-normalised book,
where leverage scales return and cost alike, so net Sharpe here does not
depend on account size.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.costs import cheapest                                    # noqa: E402
from scripts.reversal_by_session import build, weights, sharpe, TD # noqa: E402

# hourly symbol -> micro contract, for its real round-trip cost
MICRO = {"ES": "MES", "NQ": "MNQ", "YM": "MYM", "GC": "MGC", "SI": "SIL",
         "CL": "MCL", "6E": "M6E", "6A": "M6A"}
MULT = {"ES": 5, "NQ": 2, "YM": 0.5, "GC": 10, "SI": 1000, "CL": 100,
        "6E": 12500, "6A": 10000}


def side_cost_bp(C: pd.DataFrame) -> pd.DataFrame:
    """Per-side cost in bp of notional, through time, per market."""
    out = {}
    for m in C.columns:
        c = cheapest(MICRO[m])
        out[m] = c.side_usd() / (C[m] * MULT[m]) * 1e4
    return pd.DataFrame(out)


def net_returns(W, C, cost_bp):
    r = (C / C.shift(1) - 1.0)
    r = r.where(r.abs() < 0.15)
    gross = (W.shift(1) * r).sum(axis=1)
    trade = (W - W.shift(1)).abs()
    cost = (trade * cost_bp.shift(1) / 1e4).sum(axis=1)
    keep = W.shift(1).abs().sum(axis=1) > 0
    return gross[keep], (gross - cost)[keep], trade.sum(axis=1)[keep]


def main() -> int:
    O, C = build()
    W1 = weights(C)
    cb = side_cost_bp(C)
    r = (C / C.shift(1) - 1.0).where(lambda x: x.abs() < 0.15)

    print("\n--- 1. how fast does the signal decay? ---")
    print("  edge of the signal formed at close t, earned on day t+k alone")
    print(f"  {'day':>5} {'gross %/yr':>11} {'Sharpe':>8} {'t':>6}")
    for k in range(1, 8):
        p = (W1.shift(k) * r).sum(axis=1)
        p = p[W1.shift(k).abs().sum(axis=1) > 0]
        t = p.mean() / p.std() * np.sqrt(len(p))
        print(f"  t+{k:<3} {p.mean()*TD*100:+10.2f}% {sharpe(p):+8.2f} {t:+6.2f}")

    print("\n--- 2. overlapping portfolios: hold each signal N days ---")
    print(f"  {'N':>3} {'turnover/day':>13} {'gross Sharpe':>13} {'NET Sharpe':>11}"
          f" {'net %/yr':>9} {'fees % of gross':>16}")
    for N in (1, 2, 3, 4, 5, 7, 10):
        W = W1.rolling(N, min_periods=1).mean()
        g, n, t = net_returns(W, C, cb)
        fg = (g.mean() - n.mean()) / g.mean() * 100 if g.mean() > 0 else float("nan")
        print(f"  {N:>3} {t.mean():>12.2f}x {sharpe(g):>13.2f} {sharpe(n):>11.2f}"
              f" {n.mean()*TD*100:>8.2f}% {fg:>15.0f}%")

    print("\n--- 3. partial adjustment toward the target ---")
    print(f"  {'lambda':>7} {'turnover/day':>13} {'gross Sharpe':>13} {'NET Sharpe':>11}"
          f" {'net %/yr':>9}")
    for lam in (1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.10):
        W = W1.copy() * 0.0
        prev = pd.Series(0.0, index=C.columns)
        rows = []
        for t in range(len(W1)):
            tgt = W1.iloc[t]
            prev = prev + lam * (tgt - prev)
            rows.append(prev.values)
        W = pd.DataFrame(rows, index=W1.index, columns=W1.columns)
        g, n, tt = net_returns(W, C, cb)
        print(f"  {lam:>7.2f} {tt.mean():>12.2f}x {sharpe(g):>13.2f} {sharpe(n):>11.2f}"
              f" {n.mean()*TD*100:>8.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
