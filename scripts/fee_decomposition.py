#!/usr/bin/env python3
"""Where do the fees go? Per-instrument gross P&L against per-instrument cost.

Uses the REAL per-contract schedule a Phidias account pays (ares/costs.py)
rather than a flat basis-point rate, because commission is charged per
contract and so the cost of a trade in bp is commission / notional -- several
times higher on the small-notional micros.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.combined_backtest import backtest            # noqa: E402
from ares.costs import cheapest                        # noqa: E402
from ares.ledger import summarise                      # noqa: E402
from scripts.widen_universe import T1, load_panel      # noqa: E402

MULT = {m.sym: m.mult for m in T1}


def real_cost(sym, units, price):
    return (units / MULT[sym]) * cheapest(sym).side_usd()


def decompose(px, *, capital, target_vol, w_trend, maxc, cost_fn, label):
    gross = defaultdict(float)
    fees = defaultdict(float)
    trades = defaultdict(int)
    state = {"px": None, "pos": {}}

    def on_trade(ts, c, dq, price, fee):
        fees[c] += fee
        trades[c] += 1

    def on_mark(i, ts, eq, prices, led):
        if state["px"] is not None:
            for c, q in state["pos"].items():
                if q and c in prices and c in state["px"]:
                    gross[c] += q * (prices[c] - state["px"][c])
        state["px"] = dict(prices)
        state["pos"] = dict(led.pos)

    led = backtest(px, MULT, capital=capital, target_vol=target_vol,
                   w_trend=w_trend, top_k=3, max_contracts=maxc,
                   cost_fn=cost_fn, on_trade=on_trade, on_mark=on_mark,
                   warmup=1517, signal_window=1517)
    s = summarise(led)
    yrs = (px.index[-1] - px.index[1517]).days / 365.25
    G, F = sum(gross.values()), sum(fees.values())
    print(f"\n=== {label} ===")
    print(f"  net {s.ann_return_pct:+.2f}%/yr  Sharpe {s.sharpe:+.2f}  "
          f"| gross ${G/yrs:,.0f}/yr  fees ${F/yrs:,.0f}/yr  "
          f"=> fees eat {F/G*100:.0f}% of gross")
    print(f"  {'mkt':>5} {'gross $/yr':>11} {'fees $/yr':>10} {'fees/gross':>11}"
          f" {'net $/yr':>10} {'trades/yr':>10}")
    for c in sorted(gross, key=lambda k: -(gross[k] - fees[k])):
        g, f = gross[c] / yrs, fees[c] / yrs
        ratio = f"{f/g*100:9.0f}%" if g > 0 else "   (loss)"
        print(f"  {c:>5} {g:>11,.0f} {f:>10,.0f} {ratio:>11} {g-f:>10,.0f}"
              f" {trades[c]/yrs:>10.0f}")
    return s


def main() -> int:
    px = load_panel(T1)
    for w, name in ((0.0, "reversal only"), (0.5, "50/50 combined")):
        decompose(px, capital=100_000, target_vol=0.08, w_trend=w, maxc=40,
                  cost_fn=real_cost,
                  label=f"{name}, $100k, 8% vol, REAL Phidias costs")
    decompose(px, capital=100_000, target_vol=0.08, w_trend=0.0, maxc=40,
              cost_fn=None,
              label="reversal only, $100k, 8% vol, OLD flat 1.5bp model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
