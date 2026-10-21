#!/usr/bin/env python3
"""Expected value of the FX-only reversal book at FundedNext (swap-free).

Why this configuration: it is the one where every cost is either verified or
readable before purchase. FundedNext offers swap-free on every challenge with
no paperwork and confirms it for "all major Forex pairs" -- so an FX-majors
book pays no overnight swap, the unknown that decided the FTMO comparison.

Rules modelled, from fundednext.com/cfds/stellar-2-step and the help centre
(read 2026-10-21):
  * Phase 1 +8%, Phase 2 +5%, no time limit, 5 minimum trading days a phase
  * 10% maximum loss, STATIC from initial balance
  * 5% daily loss of initial balance, real time, floating losses included
  * funded: aggregate open risk (stop-loss placement plus floating losses
    across all positions) capped at 3% of initial balance. First breach
    forfeits that cycle's profit; a second cuts allowed risk to 1% for good.
  * payouts: first after 21 days, then every 14; 80% reward share
  * $549.99 for $100k, +10% for swap-free = $605

INTRADAY CHECK, deliberately pessimistic. Only daily highs and lows exist for
FX spot over 20+ years, so each day's worst intraday portfolio loss is taken
as every position hitting its worst price of the day AT THE SAME MOMENT. Real
excursions are smaller, so true pass rates are higher than shown.

Costs: spread plus commission per side, estimated at 0.3 and 0.5bp (raw-spread
EURUSD is ~0.25bp/side at FTMO's published commission). Read the real figures
from the free trial before buying.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fx_only_reversal import QUOTED, INVERT, weights   # noqa: E402

FEE = 605.0


def load_ohlc(folder="data/daily"):
    C, H, L = {}, {}, {}
    for f in QUOTED + list(INVERT):
        d = pd.read_csv(f"{folder}/{f}.csv")
        idx = (pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms"))
               + pd.Timedelta(hours=2)).normalize()
        d.index = idx
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d[(d["close"] > 0) & (d["low"] > 0)]
        n = INVERT.get(f, f[:3])
        if f in INVERT:                      # 1/x flips high and low
            C[n], H[n], L[n] = 1 / d["close"], 1 / d["low"], 1 / d["high"]
        else:
            C[n], H[n], L[n] = d["close"], d["high"], d["low"]
    C, H, L = (pd.DataFrame(x).sort_index() for x in (C, H, L))
    keep = (C.index.dayofweek < 5) & (C.notna().sum(axis=1) >= 6)
    C, H, L = C[keep].ffill(), H[keep].ffill(), L[keep].ffill()
    return C.iloc[:-1], H.iloc[:-1], L.iloc[:-1]


def day_series(side_bp):
    """Per day: (close-to-close net return, worst intraday return) at 1x."""
    C, H, L = load_ohlc()
    W, r = weights(C, k=3)
    Wl = W.shift(1)
    prev = C.shift(1)
    adverse_long = (L / prev - 1).clip(upper=0)
    adverse_short = -(H / prev - 1).clip(lower=0)
    # Yahoo's FX highs and lows contain bad ticks: a 42% "range" on EUR/USD,
    # 60% on GBP/USD, and 72 days where the range exceeded 3% while the price
    # closed almost unchanged. Left in, those phantom crashes liquidate
    # simulated accounts. Cap each day's adverse excursion at the larger of
    # that pair's own 99th-percentile range and 1.5x the day's actual close
    # move -- so genuine violent days (the 2015 franc de-peg CLOSED 20% away)
    # survive, and spikes that closed back within a fraction do not.
    rng_q = ((H - L) / prev).quantile(0.99)
    cc = (C / prev - 1).abs()
    cap = np.maximum(rng_q.values[None, :], 1.5 * cc.values)
    adverse_long = adverse_long.clip(lower=-pd.DataFrame(cap, index=C.index,
                                                         columns=C.columns))
    adverse_short = adverse_short.clip(lower=-pd.DataFrame(cap, index=C.index,
                                                           columns=C.columns))
    worst = (Wl.clip(lower=0) * adverse_long
             + (-Wl.clip(upper=0)) * adverse_short.abs() * -1).sum(axis=1)
    gross = (Wl * r).sum(axis=1)
    cost = (W - Wl).abs().sum(axis=1) * side_bp / 1e4
    live = Wl.abs().sum(axis=1) > 0
    net = (gross - cost)[live]
    worst = np.minimum(worst[live] - cost[live], net)   # worst <= close
    return net.to_numpy(), worst.to_numpy()


def simulate(net, worst, vol, *, n_paths=2000, horizon=504, seed=9,
             intraday=True):
    scale = vol / (net.std() * np.sqrt(252))
    rng = np.random.default_rng(seed)
    n = len(net)
    if not intraday:              # optimistic bound: closing balances only
        worst = np.minimum(net, 0.0)

    def draw(m):
        out, i = [], rng.integers(n)
        while len(out) < m:
            out.append(i)
            i = rng.integers(n) if rng.random() < 0.1 else (i + 1) % n
        return out

    def phase(target):
        eq, days = 1.0, 0
        for d, j in enumerate(draw(horizon), 1):
            start = eq
            if eq * (1 + worst[j] * scale) <= max(0.90, start - 0.05):
                return False, d
            eq *= 1 + net[j] * scale
            if eq - 1.0 >= target and d >= 5:
                return True, d
        return False, horizon

    def funded():
        eq, paid, warnings, risk_scale, cycle_profit = 1.0, 0.0, 0, 1.0, 0.0
        next_pay, d = 21, 0
        for d, j in enumerate(draw(horizon), 1):
            s = scale * risk_scale
            lo = eq * (1 + worst[j] * s)
            if lo <= max(0.90, eq - 0.05):
                return paid, True
            if (eq - lo) > 0.03 * risk_scale:         # 3% open-risk cap
                warnings += 1
                cycle_profit = 0.0                    # cycle profit forfeited
                if warnings >= 2:
                    risk_scale = 1.0 / 3.0            # cut to 1% for good
            before = eq
            eq *= 1 + net[j] * s
            cycle_profit += eq - before
            if d >= next_pay:
                take = max(0.0, min(eq - 1.02, cycle_profit))
                if take > 0:
                    paid += take * 0.80 * 100_000
                    eq -= take
                cycle_profit, next_pay = 0.0, d + 14
        return paid, False

    passes, pays, days = 0, [], []
    for _ in range(n_paths):
        ok1, d1 = phase(0.08)
        if not ok1:
            continue
        ok2, d2 = phase(0.05)
        if not ok2:
            continue
        passes += 1
        days.append(d1 + d2)
        p, _ = funded()
        pays.append(p)
    pr = passes / n_paths
    mp = float(np.mean(pays)) if pays else 0.0
    return pr, mp, pr * mp - FEE, (float(np.median(days)) if days else np.nan)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=2000)
    a = ap.parse_args()
    print(f"\nFundedNext Stellar 2-Step $100k, swap-free, FX-majors reversal")
    print(f"fee ${FEE:.0f}; 2 years per phase; bad ticks removed")
    print("'pessimistic' = every leg at its worst price at once (true is better)")
    print("'optimistic'  = closing balances only (true is worse)\n")
    print(f"  {'cost':>5} {'Sharpe':>7} {'vol':>4} | {'pessimistic':^24} | {'optimistic':^24}")
    print(f"  {'':>5} {'':>7} {'':>4} | {'pass':>6} {'paid':>8} {'EV':>8} | {'pass':>6} {'paid':>8} {'EV':>8}")
    rows = [(bp, None) for bp in (0.3, 0.5)] + [(0.3, "zero")]
    for bp, ctl in rows:
        net, worst = day_series(bp)
        if ctl:
            m = net.mean(); net, worst = net - m, worst - m
        sh = net.mean() / net.std() * np.sqrt(252)
        for vol in (0.06, 0.08, 0.10):
            p = simulate(net, worst, vol, n_paths=a.paths, intraday=True)
            o = simulate(net, worst, vol, n_paths=a.paths, intraday=False)
            lab = "ZERO" if ctl else f"{bp:.1f}bp"
            print(f"  {lab:>5} {sh:>+7.2f} {vol*100:>3.0f}% | {p[0]*100:>5.1f}% ${p[1]:>7,.0f}"
                  f" ${p[2]:>7,.0f} | {o[0]*100:>5.1f}% ${o[1]:>7,.0f} ${o[2]:>7,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
