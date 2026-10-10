#!/usr/bin/env python3
"""Hunt for a second, UNCORRELATED edge. Correlation is the output, not Sharpe.

Breadth failed (docs/UNIVERSE_WIDENING.md). Speed failed
(docs/HOURLY_REVERSAL_RETEST.md). Independence is what is left, and the
arithmetic is unforgiving: k streams of equal Sharpe s combine to s*sqrt(k),
so 1.2 from 0.54 takes about five independent edges. One more leg reaches
0.76. A NEGATIVELY correlated leg is worth much more -- two 0.54 edges at
r=-0.3 combine to 0.91 -- which is why value, negatively correlated with
momentum by construction, is the most interesting candidate in the slate.

Every candidate is specified in ares/edges.py from its published form before
being measured, and every one is reported whether it worked or not. All run
through the SAME sizing, cost and ledger path, so the correlations between
their return streams are comparable rather than artifacts of different
harnesses.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.combined_backtest import backtest                    # noqa: E402
from ares.edges import EDGES, MAX_LOOKBACK                     # noqa: E402
from ares.ledger import summarise                              # noqa: E402
from scripts.widen_universe import T1, load_panel              # noqa: E402

TD = 252


def returns_of(led) -> pd.Series:
    eq = np.array([e for _, e in led.curve], float)
    ts = pd.to_datetime([t for t, _ in led.curve], unit="ms")
    return pd.Series(np.diff(eq) / eq[:-1], index=ts[1:])


def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(TD)) if r.std() else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=1_000_000.0)
    ap.add_argument("--target-vol", type=float, default=0.03)
    ap.add_argument("--top-k", type=int, default=3)
    a = ap.parse_args()

    px = load_panel(T1)
    mult = {m.sym: m.mult for m in T1 if m.sym in px.columns}
    print(f"{len(px.columns)} tradeable markets, {px.index[0].date()} -> "
          f"{px.index[-1].date()}")
    # Every edge must start on the SAME bar, or the correlations compare
    # different periods. Value needs six years of history, so all of them
    # wait for it.
    print(f"common warmup {MAX_LOOKBACK} bars (~6yr, set by value's lookback)")

    streams, rows = {}, []
    for name, fn in EDGES.items():
        led = backtest(px, mult, capital=a.capital, target_vol=a.target_vol,
                       top_k=a.top_k, max_contracts=100_000,
                       warmup=MAX_LOOKBACK, signal_window=MAX_LOOKBACK,
                       signal_fn=fn)
        r = returns_of(led)
        streams[name] = r
        s = summarise(led)
        h = len(r) // 2
        rows.append((name, s, sharpe(r), sharpe(r[:h]), sharpe(r[h:])))

    print(f"\n{'edge':10s} {'ret/yr':>8} {'vol':>7} {'Sharpe':>8} {'+/-':>5}"
          f" {'t':>6} {'IS':>6} {'OOS':>6} {'maxDD':>7}")
    print("-" * 74)
    for name, s, sh, is_, oos in sorted(rows, key=lambda x: -x[2]):
        print(f"{name:10s} {s.ann_return_pct:+7.2f}% {s.ann_vol_pct:6.2f}%"
              f" {sh:+8.2f} {s.sharpe_stderr:5.2f} {s.sharpe_t:+6.2f}"
              f" {is_:+6.2f} {oos:+6.2f} {s.max_drawdown_pct:6.1f}%")

    df = pd.DataFrame(streams).dropna()
    print(f"\ncorrelation between the return streams ({len(df):,} common days)")
    c = df.corr()
    print("          " + "".join(f"{n:>9s}" for n in c.columns))
    for n in c.index:
        print(f"{n:10s}" + "".join(
            f"{c.loc[n, m]:+9.2f}" if n != m else f"{'-':>9s}"
            for m in c.columns))

    # The pair test: what does each candidate add to the EXISTING earner?
    base = "xsrev"
    print(f"\nwhat each adds to '{base}' (equal risk, both at unit vol)")
    print(f"  {'edge':10s} {'own Sharpe':>11} {'corr':>7} {'combined':>9}"
          f" {'gain':>7}")
    b = df[base] / df[base].std()
    sb = sharpe(df[base])
    for name in df.columns:
        if name == base:
            continue
        o = df[name] / df[name].std()
        r = float(df[base].corr(df[name]))
        comb = sharpe(b + o)
        print(f"  {name:10s} {sharpe(df[name]):+11.2f} {r:+7.2f}"
              f" {comb:+9.2f} {comb - sb:+7.2f}")
    print(f"\n  '{base}' alone: {sb:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
