#!/usr/bin/env python3
"""Expected value of a Phidias Premium attempt, with the two corrections that
the first simulation (scripts/prop_firm_study.py) got wrong.

1. INTRADAY BREACH. Phidias sets the drawdown floor at the end of each day
   but liquidates the moment the balance touches it DURING the day ("if your
   balance reaches and exceeds the value of your drawdown limit, you will be
   liquidated"). The first simulation only checked closing balances, which
   ignores every intraday dip and overstates the pass rate. This one walks
   each simulated day hour by hour.

2. REAL COSTS. The first simulation used a flat 1.5bp model. Phidias charges
   per contract, which costs this book far more (fees ~60% of gross). Here
   each day's turnover is charged at the per-contract schedule.

Also uses the actual price: $180 one-time with the firm's own advertised code
(PHIDIAS80) and the $149 activation waived on one-time payment -- not the
$450 + $149 list price the first simulation charged.

The strategy's hourly P&L path comes from real Databento hourly prices:
positions are set at each 16:00 New York close and the book is marked every
hour until the next close. Whole days (hour vectors) are block-bootstrapped,
so overnight gaps and intraday swings stay attached to the days they
happened on.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.costs import cheapest                                    # noqa: E402
from scripts.prop_firm_study import PHIDIAS_100K, Rules            # noqa: E402

EIGHT = ["ES", "NQ", "YM", "GC", "SI", "CL", "6E", "6A"]
MICRO = {"ES": ("MES", 5), "NQ": ("MNQ", 2), "YM": ("MYM", 0.5),
         "GC": ("MGC", 10), "SI": ("SIL", 1000), "CL": ("MCL", 100),
         "6E": ("M6E", 12500), "6A": ("M6A", 10000)}
CLOSE_H = 20          # 16:00 New York in UTC (summer); the book's rebalance
FEE = 180.0           # one-time, with code; activation waived


def hourly_panel():
    cols = {}
    for m in EIGHT:
        d = pd.read_csv(f"data/futures_db_1h/{m}.csv")
        s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
        s = s[~s.index.duplicated(keep="last")].sort_index()
        g = pd.date_range(s.index[0].floor("h"), s.index[-1].ceil("h"), freq="h")
        cols[m] = s.reindex(g).ffill(limit=3)
    return pd.DataFrame(cols).dropna(thresh=6)


def day_paths(cost_mult: float = 1.0):
    """List of per-day hourly return vectors for the reversal book (unit vol
    not yet applied), net of that day's trading cost at the close."""
    H = hourly_panel()
    closes = H[H.index.hour == CLOSE_H]
    closes = closes[closes.index.dayofweek < 5]
    rc = closes.pct_change().where(lambda x: x.abs() < 0.15)
    vol = rc.rolling(60, min_periods=30).std()
    side_bp = {m: cheapest(MICRO[m][0]).side_usd() for m in EIGHT}
    paths, prev_w = [], pd.Series(0.0, index=EIGHT)
    idx = closes.index
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
        # cost of moving from yesterday's book to today's, in return terms
        px = closes.iloc[t]
        cost = sum(abs(w[m] - prev_w[m]) * side_bp[m] / (px[m] * MICRO[m][1])
                   for m in EIGHT if np.isfinite(px[m]))
        prev_w = w
        seg = H.loc[idx[t]:idx[t + 1]]
        hr = seg.pct_change().iloc[1:].where(lambda z: z.abs() < 0.10).fillna(0.0)
        path = (hr * w).sum(axis=1).to_numpy().copy()
        if len(path) == 0:
            continue
        path[-1] -= cost * cost_mult
        paths.append(path)
    return paths


def simulate(paths, k: Rules, vol, *, intraday=True, horizon=252,
             n_paths=1500, block=10, buffer=1000.0, seed=3):
    daily = np.array([np.prod(1 + p) - 1 for p in paths])
    scale = vol / (daily.std() * np.sqrt(252))
    rng = np.random.default_rng(seed)
    n = len(paths)

    def draw(m):
        out, i = [], rng.integers(n)
        while len(out) < m:
            out.append(i)
            i = rng.integers(n) if rng.random() < 1 / block else (i + 1) % n
        return out

    def walk(days, eq, hwm, lock, funded):
        """Returns (state, day_index_when_done)."""
        paid, q, npay = 0.0, 0, 0
        for d, j in enumerate(days, 1):
            before = eq
            floor = min(hwm - k.drawdown, lock) if funded else hwm - k.drawdown
            for r in paths[j] * scale:
                eq *= 1 + r
                if intraday and eq <= floor:
                    return ("breach", d, paid)
            if not intraday and eq <= floor:
                return ("breach", d, paid)
            hwm = max(hwm, eq)
            if not funded and eq - k.size >= k.profit_target:
                return ("pass", d, paid)
            if funded:
                if eq - before >= k.payout_min_day_pnl:
                    q += 1
                if q >= k.payout_every and eq >= k.payout_threshold:
                    take = min(k.payout_cap, eq - (k.payout_floor + buffer))
                    if take >= 500:
                        paid += take * k.splits[min(npay, len(k.splits) - 1)]
                        eq -= take
                        npay += 1
                        q = 0
        return ("alive", len(days), paid)

    passes, pay, breach_f = 0, [], 0
    for _ in range(n_paths):
        st, d, _ = walk(draw(horizon), k.size, k.size, np.inf, False)
        if st != "pass":
            continue
        passes += 1
        st2, _, paid = walk(draw(horizon), k.size, k.size, k.dd_locks_at, True)
        pay.append(paid)
        breach_f += st2 == "breach"
    pr = passes / n_paths
    mp = float(np.mean(pay)) if pay else 0.0
    return pr, mp, (breach_f / passes if passes else float("nan")), pr * mp - FEE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=1500)
    a = ap.parse_args()
    paths = day_paths()
    daily = np.array([np.prod(1 + p) - 1 for p in paths])
    print(f"\n{len(paths):,} real trading days of hourly paths, "
          f"net Sharpe of the book {daily.mean()/daily.std()*np.sqrt(252):+.2f} "
          f"(real per-contract costs)")
    print(f"Phidias Premium 100K, fee ${FEE:.0f}, eval within 1 year\n")
    print(f"  {'vol':>5} | {'EOD-only check (old sim)':^30} | {'INTRADAY check (Phidias)':^30}")
    print(f"  {'':>5} | {'pass':>6} {'paid/yr':>9} {'EV':>9}   | {'pass':>6} {'paid/yr':>9} {'EV':>9}")
    for vol in (0.03, 0.05, 0.08, 0.12, 0.18):
        e = simulate(paths, PHIDIAS_100K, vol, intraday=False, n_paths=a.paths)
        i = simulate(paths, PHIDIAS_100K, vol, intraday=True, n_paths=a.paths)
        print(f"  {vol*100:4.0f}% | {e[0]*100:5.1f}% ${e[1]:>8,.0f} ${e[3]:>8,.0f}"
              f"   | {i[0]*100:5.1f}% ${i[1]:>8,.0f} ${i[3]:>8,.0f}")

    print("\n  Same, with GROSS returns (as if trading were free) -- the ceiling:")
    gp = day_paths(cost_mult=0.0)
    for vol in (0.08, 0.12, 0.18):
        i = simulate(gp, PHIDIAS_100K, vol, intraday=True, n_paths=a.paths)
        print(f"  {vol*100:4.0f}%   pass {i[0]*100:5.1f}%  paid/yr ${i[1]:>7,.0f}  EV ${i[3]:>7,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
