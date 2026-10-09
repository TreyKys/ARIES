#!/usr/bin/env python3
"""Hourly cross-sectional reversal on the markets that DO have a daily edge.

Hourly reversal across 16 CME markets was tested and rejected: out-of-sample
Sharpe 0.32, t=0.76 over 15 years -- indistinguishable from nothing. That test
pointed the signal at every market in the file. The daily work since then
found that only eight markets carry a measurable reversal edge, and that the
other eleven tradeable ones carry none (Sharpe +0.13, OOS -0.03; see
docs/UNIVERSE_WIDENING.md). So the earlier rejection may have measured eight
good streams diluted by eight empty ones rather than the absence of an edge.

This re-points the same test at the eight.

HONEST CAVEAT, stated before the result. Choosing these eight BECAUSE they
showed a daily edge is a selection made on overlapping data, so this is not a
clean out-of-sample test of "does hourly reversal work". Two things limit the
damage, neither of them eliminates it:
  * the selection was made at a different horizon (daily) from the test
    (hourly), so the two are not measuring the same thing;
  * the configuration is still chosen in-sample and reported out-of-sample,
    and there is a final holdout below that no earlier test has touched.
Read a positive result here as "worth a clean test", never as proof.

THE HOLDOUT. The Databento panel ends 2025-12-31. A separate Yahoo pull covers
2024-05 to 2026-10, so calendar 2026 is data no test in this repo has ever
seen. The configuration is frozen before it is run.

The decisive number is BREAKEVEN COST -- the round-trip cost at which the
gross edge is exactly consumed -- against the 0.34-0.75bp a micro futures
account actually pays.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.ledger import summarise                                  # noqa: E402
from ares.xsreversal import breakeven_from, run_xs_reversal        # noqa: E402

# The eight with a measured daily reversal edge, as hourly symbols.
EIGHT = ["ES", "NQ", "YM", "GC", "SI", "CL", "6E", "6A"]
BARS_YR = 24 * 365
COST_BPS = 0.75          # measured micro-futures round trip


def panel(folder: str, symbols=None) -> pd.DataFrame:
    cols = {}
    for p in sorted(Path(folder).glob("*.csv")):
        name = p.stem
        if symbols and name not in symbols:
            continue
        d = pd.read_csv(p)
        s = pd.Series(d["close"].values,
                      index=pd.to_datetime(d["ts"], unit="ms"))
        s = s[~s.index.duplicated(keep="last")].sort_index()
        cols[name] = s[s > 0]
    px = pd.DataFrame(cols).sort_index()
    # Require most of the cross-section present: demeaning against two
    # surviving markets is not a market factor, it is noise.
    px = px.dropna(axis=0, thresh=max(5, int(len(px.columns) * 0.75)))
    # Blank implausible moves and their neighbours -- roll gaps, and the
    # mirror image the reversal leg would otherwise collect on the next bar.
    r = px.pct_change()
    bad = r.abs() > 0.10
    bad = bad | bad.shift(-1).fillna(False) | bad.shift(1).fillna(False)
    return px.mask(bad)


def run(px, look, hold, k, cost=0.0):
    return run_xs_reversal(px, lookback=look, hold=hold, top_k=k,
                           cost_bps=cost, capital=100_000.0,
                           bars_per_year=BARS_YR, min_universe=5)


def line(tag, px, look, hold, k):
    zero = run(px, look, hold, k, 0.0)
    be = breakeven_from(zero)
    net = run(px, look, hold, k, COST_BPS)
    s = summarise(net.ledger, periods_per_year=BARS_YR)
    print(f"  {tag:22s} look{look:>3} hold{hold:>3} k{k:>2} |"
          f" gross {zero.gross_return_pct:+8.2f}%/yr  breakeven {be:6.2f}bp |"
          f" net@{COST_BPS}bp {s.ann_return_pct:+8.2f}%/yr"
          f"  Sharpe {s.sharpe:+5.2f} +/-{s.sharpe_stderr:4.2f}"
          f" (t={s.sharpe_t:+5.2f})")
    return be, s


def decay(px, L, H, K):
    """Gross edge (before ANY cost) by 3-year block.

    If the out-of-sample failure were a cost problem, the gross edge would
    still be there. If gross itself goes negative, no cost reduction can save
    it -- and the shape across blocks says whether it decayed or never existed.
    """
    print("\n--- 5. gross edge by period, BEFORE costs ---")
    print(f"  {'period':>14} {'bars':>8} {'gross %/yr':>12} {'breakeven':>11}")
    for start in range(2011, 2026, 3):
        blk = px.loc[f"{start}-01-01":f"{start+2}-12-31"]
        if len(blk) < 2000:
            continue
        z = run(blk, L, H, K, 0.0)
        print(f"  {start}-{start+2:>4} {len(blk):8,} "
              f"{z.gross_return_pct:+11.2f}% {breakeven_from(z):10.2f}bp")


def main() -> int:
    full = panel("data/futures_db_1h")
    eight = panel("data/futures_db_1h", EIGHT)
    yrs = (eight.index[-1] - eight.index[0]).days / 365.25
    print(f"\nDatabento hourly: {len(full.columns)} markets all / "
          f"{len(eight.columns)} selected, {len(eight):,} bars, {yrs:.1f}yr")

    split = eight.index[0] + pd.Timedelta(days=int(365.25 * 9))
    is_8, oos_8 = eight.loc[:split], eight.loc[split:]
    is_a, oos_a = full.loc[:split], full.loc[split:]
    print(f"IS {is_8.index[0].date()}->{is_8.index[-1].date()} | "
          f"OOS {oos_8.index[0].date()}->{oos_8.index[-1].date()}")

    print("\n--- 1. choose the configuration IN-SAMPLE, on the eight ---")
    best, grid = None, []
    for look in (1, 2, 4, 8, 24):
        for hold in (1, 2, 4, 8, 24):
            for k in (2, 3):
                z = run(is_8, look, hold, k, 0.0)
                be = breakeven_from(z)
                grid.append((be, look, hold, k, z.gross_return_pct))
                if best is None or be > best[0]:
                    best = (be, look, hold, k)
    grid.sort(reverse=True)
    for be, look, hold, k, g in grid[:5]:
        print(f"    look{look:>3} hold{hold:>3} k{k:>2}  breakeven {be:6.2f}bp"
              f"  gross {g:+9.2f}%/yr")
    _, L, H, K = best
    print(f"  chosen in-sample: look={L} hold={H} k={K}")

    print(f"\n--- 2. OUT OF SAMPLE with that frozen configuration ---")
    be8, s8 = line("eight markets OOS", oos_8, L, H, K)
    bea, sa = line("all 20 markets OOS", oos_a, L, H, K)

    print("\n--- 3. for reference: the same config IN-sample ---")
    line("eight markets IS", is_8, L, H, K)
    line("all 20 markets IS", is_a, L, H, K)

    print("\n--- 4. HOLDOUT: calendar 2026, never used by any earlier test ---")
    y = panel("data/futures_1h", EIGHT)
    y26 = y.loc["2026-01-01":]
    if len(y26) > 500:
        print(f"  {len(y26):,} bars, "
              f"{y26.index[0].date()} -> {y26.index[-1].date()}")
        line("eight markets 2026", y26, L, H, K)
    else:
        print(f"  too little 2026 data ({len(y26)} bars)")

    decay(eight, L, H, K)
    print(f"\n  Verdict rests on breakeven vs the {COST_BPS}bp actually paid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
