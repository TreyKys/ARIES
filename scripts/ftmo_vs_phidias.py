#!/usr/bin/env python3
"""Same edge, different venue: FTMO 2-Step Swing (CFDs) against Phidias
Premium (futures). The question is whether the VENUE's structure, not the
strategy, decides whether this edge can pay.

Why the venue could matter more than the strategy:

  * GATE SHAPE. Phidias: make 6% before a 3% TRAILING drawdown -- a 2:1 bet
    that a weak edge passes about as often as a coin weighted by that ratio.
    FTMO 2-Step: make 10% before a 10% STATIC loss, then 5% before the same
    static 10% -- 1:1 then 1:2, with a floor that never moves up.

  * COST STRUCTURE. Phidias charges a fixed dollar commission PER CONTRACT,
    and its 3% drawdown forces the smallest contracts, which are the most
    expensive per dollar traded. CFDs trade in fractional lots with cost
    proportional to notional (spread, plus a per-lot commission on FX only),
    so small size carries no penalty. But CFDs charge an overnight SWAP, and
    this book holds every position overnight -- that is where 78% of its
    edge is earned. FTMO does not publish swap rates outside its platform,
    so the swap markup is a PARAMETER here, not a guess presented as fact.

Verified (ftmo.com/en/how-it-works, 2026-10-13): Phase 1 +10%, Phase 2 +5%,
5% maximum daily loss, 10% maximum loss, Swing allows overnight and weekend
holding, fee refunded with the first reward, up to 90% split (80% used here,
the pre-scaling level). FX commission $2.50/lot/side (FTMO trading update,
Sep 2025); indices commission-free.

ESTIMATED, not verified: CFD spreads per instrument, the gold/silver fee, the
swap markup, the $590 fee. Every one can be read off FTMO's free trial
account before a cent is spent; the output table says which matter.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phidias_true_ev import (EIGHT, CLOSE_H, hourly_panel,    # noqa: E402
                                     day_paths as phidias_paths, simulate,
                                     PHIDIAS_100K, FEE as PHIDIAS_FEE)

# Estimated CFD cost per side, basis points of notional (half spread plus any
# commission). FX includes FTMO's $2.50/lot/side on a 100k-unit lot.
FTMO_SIDE_BP = {"ES": 0.30, "NQ": 0.25, "YM": 0.30, "GC": 0.35,
                "SI": 2.0, "CL": 2.3, "6E": 0.33, "6A": 0.68}
FTMO_FEE = 590.0                     # ~EUR 540; refunded with first reward


def cfd_paths(cost_mult=1.0, swap_markup=0.015):
    """Hourly day paths for the same book, CFD cost model.

    swap_markup: annual cost charged on GROSS exposure for every night held.
    A long CFD typically pays the benchmark rate plus a markup and a short
    receives the rate minus it, so for a long/short book the benchmark nets
    out and roughly the markup is paid on the whole gross position.
    """
    H = hourly_panel()
    closes = H[H.index.hour == CLOSE_H]
    closes = closes[closes.index.dayofweek < 5]
    rc = closes.pct_change().where(lambda x: x.abs() < 0.15)
    vol = rc.rolling(60, min_periods=30).std()
    paths, prev, idx = [], pd.Series(0.0, index=EIGHT), closes.index
    for t in range(61, len(idx) - 1):
        x = rc.iloc[t].dropna()
        if len(x) < 6:
            continue
        x = x - x.mean()
        o = x.sort_values().index
        w = pd.Series(0.0, index=EIGHT)
        w[o[:3]], w[o[-3:]] = 1.0, -1.0
        w = (w / vol.iloc[t].where(vol.iloc[t] > 0)).fillna(0.0)
        g = w.abs().sum()
        if not g:
            continue
        w = w / g
        trade = sum(abs(w[m] - prev[m]) * FTMO_SIDE_BP[m] / 1e4 for m in EIGHT)
        prev = w
        nights = max(1, (idx[t + 1] - idx[t]).days)     # a weekend is 3
        swap = swap_markup / 360.0 * nights * w.abs().sum()
        seg = H.loc[idx[t]:idx[t + 1]]
        hr = seg.pct_change().iloc[1:].where(lambda z: z.abs() < 0.10).fillna(0.0)
        path = (hr * w).sum(axis=1).to_numpy().copy()
        if len(path) == 0:
            continue
        path[0] -= swap
        path[-1] -= trade * cost_mult
        paths.append(path)
    return paths


def ftmo(paths, vol, *, n_paths=1000, horizon=504, payout_every=14,
         split=0.80, buffer=0.02, seed=5):
    """2-Step Swing: P1 +10%, P2 +5%, then funded. Static 10% max loss and a
    5% daily loss, both checked HOURLY against intraday equity."""
    daily = np.array([np.prod(1 + p) - 1 for p in paths])
    scale = vol / (daily.std() * np.sqrt(252))
    rng = np.random.default_rng(seed)
    n = len(paths)

    def draw(m):
        out, i = [], rng.integers(n)
        while len(out) < m:
            out.append(i)
            i = rng.integers(n) if rng.random() < 0.1 else (i + 1) % n
        return out

    def phase(target, funded=False):
        eq, paid, days, first_pay = 1.0, 0.0, 0, None
        floor = 0.90
        for d, j in enumerate(draw(horizon), 1):
            day_floor = eq - 0.05
            for r in paths[j] * scale:
                eq *= 1 + r
                if eq <= floor or eq <= day_floor:
                    return False, d, paid, first_pay
            if not funded and eq - 1.0 >= target:
                return True, d, paid, first_pay
            if funded and d % payout_every == 0 and eq > 1.0 + buffer:
                take = eq - (1.0 + buffer)
                paid += take * split * 100_000
                eq -= take
                first_pay = first_pay or d
        return (funded, horizon, paid, first_pay)

    passed, pays, refunds, days = 0, [], 0, []
    for _ in range(n_paths):
        ok1, d1, _, _ = phase(0.10)
        if not ok1:
            continue
        ok2, d2, _, _ = phase(0.05)
        if not ok2:
            continue
        passed += 1
        days.append(d1 + d2)
        _, _, paid, first = phase(None, funded=True)
        pays.append(paid)
        refunds += first is not None
    pr = passed / n_paths
    mp = float(np.mean(pays)) if pays else 0.0
    refund = (refunds / passed if passed else 0.0) * FTMO_FEE
    ev = pr * (mp + refund) - FTMO_FEE
    return pr, mp, ev, (np.median(days) if days else float("nan"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=800)
    a = ap.parse_args()

    ph = phidias_paths()
    s = lambda P: (lambda d: d.mean() / d.std() * np.sqrt(252))(
        np.array([np.prod(1 + p) - 1 for p in P]))
    print(f"\nnet Sharpe of the book -- Phidias futures costs: {s(ph):+.2f}")
    grid = {}
    for sw in (0.0, 0.015, 0.03):
        for cm in (0.5, 1.0, 1.5):
            grid[(sw, cm)] = cfd_paths(cost_mult=cm, swap_markup=sw)
    print("net Sharpe of the book -- FTMO CFD costs:")
    print(f"  {'swap markup/yr':>15} | {'spreads x0.5':>12} {'x1.0 (est.)':>12} {'x1.5':>8}")
    for sw in (0.0, 0.015, 0.03):
        print(f"  {sw*100:>14.1f}% | " + " ".join(
            f"{s(grid[(sw, cm)]):>+12.2f}" if cm < 1.5 else f"{s(grid[(sw, cm)]):>+8.2f}"
            for cm in (0.5, 1.0, 1.5)))

    print(f"\nExpected value per attempt (intraday-checked limits, 2-year horizon)")
    print(f"  Phidias Premium 100K: fee ${PHIDIAS_FEE:.0f}, best of 5 vol levels")
    best = max((simulate(ph, PHIDIAS_100K, v, intraday=True, n_paths=a.paths, horizon=504)
                + (v,)) for v in (0.05, 0.08, 0.12, 0.18))
    print(f"    vol {best[4]*100:.0f}%: pass {best[0]*100:.1f}%  EV ${best[3]:,.0f}")
    print(f"\n  FTMO 2-Step Swing 100K: fee ${FTMO_FEE:.0f}, refunded on first payout")
    print(f"  {'swap':>6} {'spreads':>8} {'vol':>5} {'pass':>7} {'median days':>12}"
          f" {'paid (2yr)':>11} {'EV':>8}")
    for sw in (0.0, 0.015, 0.03):
        for cm in (1.0,):
            for v in (0.06, 0.10, 0.15):
                pr, mp, ev, md = ftmo(grid[(sw, cm)], v, n_paths=a.paths)
                print(f"  {sw*100:5.1f}% {'est.':>8} {v*100:4.0f}% {pr*100:6.1f}%"
                      f" {md:>12.0f} ${mp:>10,.0f} ${ev:>7,.0f}")
    print("\n  For reference -- FTMO with trading made FREE (no spread, no swap):")
    free = cfd_paths(cost_mult=0.0, swap_markup=0.0)
    for v in (0.06, 0.10, 0.15):
        pr, mp, ev, md = ftmo(free, v, n_paths=a.paths)
        print(f"  {'free':>15} {v*100:4.0f}% {pr*100:6.1f}% {md:>12.0f} ${mp:>10,.0f} ${ev:>7,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
