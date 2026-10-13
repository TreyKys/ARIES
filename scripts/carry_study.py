#!/usr/bin/env python3
"""Is carry a second edge -- and does it escape the fee trap?

The fee work closed one door firmly: the one-day reversal edge must rebuild
the book every day, and Phidias's fixed per-contract commission alone costs
it about 0.25 of Sharpe. No execution trick recovers more than the spread.
An edge that DOESN'T need turnover is the only exit, and carry is the
canonical one: rebalanced monthly.

Specified in advance, from Koijen, Moskowitz, Pedersen & Vrugt (2018), and
not tuned afterwards:
  * carry smoothed over 21 days, measured at each month end
  * divided by each market's own volatility, so a 22% crude carry and a 1%
    euro carry are compared on one scale (and so the irregular contract gaps
    of serially-listed FX and metals cannot distort the ranking)
  * cross-sectional: long the 3 highest, short the 3 lowest, inverse-vol
  * time-series variant: long every market in backwardation, short contango
  * held for the month; costs from Phidias's per-contract schedule

Reported against the reversal book built from the SAME Databento prices, so
the correlation between the two is measured on identical days and data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.carry_signal import load_panel                     # noqa: E402
from ares.costs import cheapest                              # noqa: E402

TD = 252
MICRO = {"ES": ("MES", 5), "NQ": ("MNQ", 2), "YM": ("MYM", 0.5),
         "RTY": ("M2K", 5), "GC": ("MGC", 10), "SI": ("SIL", 1000),
         "CL": ("MCL", 100), "6E": ("M6E", 12500), "6A": ("M6A", 10000),
         "6B": ("M6B", 6250)}
TRADEABLE = list(MICRO)                       # micro on Phidias's schedule
RESEARCH = TRADEABLE + ["HG", "6J", "ZN", "ZB"]
GENERIC_SIDE_BP = 1.5                         # roots with no Phidias micro


def side_bp(root, level):
    if root in MICRO:
        sym, mult = MICRO[root]
        return cheapest(sym).side_usd() / (level * mult) * 1e4
    return pd.Series(GENERIC_SIDE_BP, index=level.index)


def price_levels(roots):
    """Front-contract price, for converting dollar costs to bp."""
    from ares.carry_signal import load_root
    return pd.DataFrame({r: load_root(r)["p0"] for r in roots})


def xs_weights(score: pd.Series, vol: pd.Series, k: int) -> pd.Series:
    s = score.replace([np.inf, -np.inf], np.nan).dropna()
    w = pd.Series(0.0, index=score.index)
    if len(s) < 6:
        return w
    order = s.sort_values().index
    w[order[-k:]] = 1.0
    w[order[:k]] = -1.0
    w = (w / vol.where(vol > 0)).fillna(0.0)
    g = w.abs().sum()
    return w / g if g else w


def carry_book(R, K, roots, k=3, kind="xs"):
    vol = R[roots].rolling(60, min_periods=30).std()
    ksm = K[roots].rolling(21, min_periods=10).mean()
    month_end = R.index.to_series().groupby(
        [R.index.year, R.index.month]).transform("max") == R.index.to_series()
    W = pd.DataFrame(np.nan, index=R.index, columns=roots)
    for t in np.where(month_end.values)[0]:
        if t < 60:
            continue
        v = vol.iloc[t]
        if kind == "xs":
            W.iloc[t] = xs_weights(ksm.iloc[t] / (v * np.sqrt(TD)), v, k)
        else:                                   # time-series: sign of carry
            w = (np.sign(ksm.iloc[t]) / v.where(v > 0)).fillna(0.0)
            g = w.abs().sum()
            W.iloc[t] = w / g if g else w
    return W.ffill().fillna(0.0)


def reversal_book(R, roots, k=3):
    vol = R[roots].rolling(60, min_periods=30).std()
    W = pd.DataFrame(0.0, index=R.index, columns=roots)
    for t in range(61, len(R)):
        x = R[roots].iloc[t].dropna()
        if len(x) < 6:
            continue
        W.iloc[t] = xs_weights(-(x - x.mean()), vol.iloc[t], k)
    return W


def run(W, R, cost_bp):
    roots = list(W.columns)
    r = R[roots]
    gross = (W.shift(1) * r).sum(axis=1)
    trade = (W - W.shift(1)).abs()
    cost = (trade * cost_bp[roots].shift(1) / 1e4).sum(axis=1)
    live = W.shift(1).abs().sum(axis=1) > 0
    return gross[live], (gross - cost)[live], trade.sum(axis=1)[live]


def sh(x):
    return float(x.mean() / x.std() * np.sqrt(TD)) if len(x) > 2 and x.std() else 0.0


def report(label, g, n, t):
    h = len(n) // 2
    tstat = n.mean() / n.std() * np.sqrt(len(n))
    print(f"  {label:34s} gross {sh(g):+5.2f}  NET {sh(n):+5.2f} (t={tstat:+5.2f})"
          f"  IS {sh(n.iloc[:h]):+5.2f} OOS {sh(n.iloc[h:]):+5.2f}"
          f"  turnover {t.mean()*TD:5.1f}x/yr  net {n.mean()*TD*100:+5.2f}%/yr")


def main() -> int:
    R, K, gaps = load_panel(RESEARCH)
    lv = price_levels(RESEARCH).reindex(R.index).ffill()
    cb = pd.DataFrame({r: side_bp(r, lv[r]) for r in RESEARCH})
    print(f"\nDatabento daily, {R.index[0].date()} -> {R.index[-1].date()}, "
          f"real Phidias per-contract costs\n")

    out = {}
    for uni_name, roots in (("tradeable 10", TRADEABLE), ("research 14", RESEARCH)):
        print(f"--- {uni_name}: {', '.join(roots)} ---")
        for kind, lab in (("xs", "carry, cross-sectional"),
                          ("ts", "carry, time-series")):
            W = carry_book(R, K, roots, kind=kind)
            g, n, t = run(W, R, cb)
            report(lab, g, n, t)
            out[(uni_name, kind)] = n
        W = reversal_book(R, roots)
        g, n, t = run(W, R, cb)
        report("reversal (1-day, for comparison)", g, n, t)
        out[(uni_name, "rev")] = n
        print()

    print("--- correlation and combination, tradeable 10 ---")
    df = pd.DataFrame({"carry_xs": out[("tradeable 10", "xs")],
                       "carry_ts": out[("tradeable 10", "ts")],
                       "reversal": out[("tradeable 10", "rev")]}).dropna()
    print(df.corr().round(2).to_string())
    for c in ("carry_xs", "carry_ts"):
        a = df["reversal"] / df["reversal"].std()
        b = df[c] / df[c].std()
        print(f"  reversal + {c} (equal risk): NET Sharpe {sh(a + b):+.2f}"
              f"   [reversal alone {sh(df['reversal']):+.2f}, "
              f"{c} alone {sh(df[c]):+.2f}]")

    print("\n--- by period, tradeable 10 (NET Sharpe) ---")
    print(f"  {'period':>11} {'carry xs':>9} {'carry ts':>9} {'reversal':>9}")
    for y in range(2011, 2027, 3):
        m = (df.index.year >= y) & (df.index.year <= y + 2)
        if m.sum() > 200:
            print(f"  {y}-{min(y+2, 2026):>4} {sh(df['carry_xs'][m]):+9.2f}"
                  f" {sh(df['carry_ts'][m]):+9.2f} {sh(df['reversal'][m]):+9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
