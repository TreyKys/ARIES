#!/usr/bin/env python3
"""Scan the crypto universe for tradeable pairs and battle-test stat-arb.

Selection (on 2024 in-sample): high correlation AND a mean-reverting
spread (finite half-life) -- looser and more robust than strict full-year
cointegration, which the first run showed selects almost nothing.
Backtest (on 2025 out-of-sample): rolling z-score spread trades, full
costs. Reports how many selected pairs stayed profitable (the real edge
signal) plus an equal-weight portfolio.

Usage: python scripts/statarb_scan.py [tf] [corr_min]   e.g. 4h 0.8
"""
import glob
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares import datasource, statarb

SPLIT = 1735689600000
FX = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GBPJPY", "USDCAD"}


def load_universe(tf):
    series = {}
    for path in sorted(glob.glob(f"data/*_{tf}.csv")):
        sym = Path(path).stem.replace(f"_{tf}", "")
        if sym in FX:
            continue
        series[sym] = datasource.load_csv(path)
    return series


def pos_months(curve):
    if len(curve) < 2:
        return 0.0
    by = {}
    for ts, eq in curve:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        by[(d.year, d.month)] = eq
    ks = sorted(by)
    rets = [by[ks[i]] / by[ks[i - 1]] - 1 for i in range(1, len(ks)) if by[ks[i - 1]] > 0]
    return (sum(1 for r in rets if r > 0) / len(rets)) if rets else 0.0


def main() -> int:
    tf = sys.argv[1] if len(sys.argv) > 1 else "1h"
    corr_min = float(sys.argv[2]) if len(sys.argv) > 2 else 0.85
    P = statarb.StatArbParams()

    series = load_universe(tf)
    ts, closes = statarb.align(series)
    syms = list(closes.keys())
    is_m, oos_m = ts < SPLIT, ts >= SPLIT
    print(f"[{tf}] Universe {len(syms)} assets | IS {is_m.sum()} bars / OOS {oos_m.sum()} bars "
          f"| {len(list(combinations(syms,2)))} pairs | corr>={corr_min}")

    # --- selection on IS: correlation + mean-reverting spread ---
    selected = []
    for a, b in combinations(syms, 2):
        ca, cb = closes[a][is_m], closes[b][is_m]
        if ca.size < P.lookback * 2:
            continue
        la, lb = np.log(ca), np.log(cb)
        corr = np.corrcoef(la, lb)[0, 1]
        if corr < corr_min:
            continue
        spread, _ = statarb.static_spread(ca, cb)
        hl = statarb.half_life(spread)
        if 2 <= hl <= P.max_hold:
            selected.append((a, b, corr, hl))
    selected.sort(key=lambda x: -x[2])
    print(f"Selected pairs (corr + half-life in [2,{P.max_hold}]): {len(selected)}")

    # --- OOS backtest ---
    results = []
    for a, b, corr, hl in selected:
        r = statarb.backtest_pair(a, b, closes[a][oos_m], closes[b][oos_m], ts[oos_m], P)
        m = r.metrics
        if m["n"] >= 5:
            results.append((a, b, r, m))
    if not results:
        print("No pairs produced >=5 OOS trades.")
        return 0

    profitable = sum(1 for *_, m in results if m["pf"] > 1)
    results.sort(key=lambda x: x[3]["sharpe"], reverse=True)
    print(f"\n{profitable}/{len(results)} selected pairs profitable OOS (PF>1). Top by Sharpe:")
    print(f"{'pair':<20}{'trades':>7}{'win%':>6}{'PF':>6}{'ret%':>8}{'sharpe':>8}{'maxDD':>7}")
    for a, b, r, m in results[:12]:
        pf = "inf" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
        print(f"{a+'/'+b:<20}{m['n']:>7}{m['win_rate']*100:>5.0f}%{pf:>6}"
              f"{m['total_ret_pct']:>+8.1f}{m['sharpe']:>8.2f}{m['max_dd_pct']:>6.1f}%")

    # --- equal-weight portfolio across selected pairs ---
    pooled = []
    for a, b, r, m in results:
        for k in range(1, len(r.equity_curve)):
            net = r.equity_curve[k][1] / r.equity_curve[k - 1][1] - 1.0
            pooled.append((r.equity_curve[k][0], net))
    pooled.sort(key=lambda x: x[0])
    n_sel = len(results)
    equity = 1.0; curve = []; rets = []
    for ts_k, net in pooled:
        scaled = net / n_sel
        equity *= (1 + scaled); rets.append(scaled); curve.append((ts_k, equity))
    eqv = np.array([e for _, e in curve])
    peak = np.maximum.accumulate(eqv)
    dd = float(np.max((peak - eqv) / peak)) * 100 if eqv.size else 0.0
    days = (curve[-1][0] - curve[0][0]) / 86_400_000 if len(curve) > 1 else 1
    ann = ((equity) ** (365 / days) - 1) * 100 if days > 0 else 0
    arr = np.array(rets); sharpe = arr.mean() / arr.std() * np.sqrt(len(arr)) if arr.std() > 0 else 0
    print("\n" + "=" * 66)
    print(f"  STAT-ARB PORTFOLIO [{tf}] equal-weight {n_sel} pairs, OOS 2025")
    print(f"  return {(equity-1)*100:+.1f}%  annualized {ann:+.1f}%  "
          f"maxDD {dd:.2f}%  +months {pos_months(curve)*100:.0f}%  Sharpe {sharpe:.2f}")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
