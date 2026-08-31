#!/usr/bin/env python3
"""Backtest delta-neutral funding-rate carry on real funding history.

    python scripts/fetch_funding.py BTCUSDT 2024-01 2025-06
    python scripts/backtest_carry.py --csv data/BTCUSDT_funding.csv --capital 50
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares.carry import CarryConfig, run_carry


def load_funding(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["ts"]), float(r["interval_hours"]), float(r["rate"])))
    rows.sort(key=lambda x: x[0])
    return rows


def show(title, res):
    m = res.metrics
    print(f"  {title:<24} return={m['total_return_pct']:+6.1f}%  "
          f"annualized={m['annualized_pct']:+6.1f}%  maxDD={m['max_drawdown_pct']:5.2f}%  "
          f"in_market={m['pct_in_market']:.0%}  final=${res.final_equity:.2f}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--capital", type=float, default=50.0)
    args = p.parse_args()

    funding = load_funding(args.csv)
    days = (funding[-1][0] - funding[0][0]) / 86_400_000
    print("=" * 78)
    print(f"  Delta-neutral funding carry  |  {args.csv}  |  ${args.capital:.2f}  |  {days:.0f} days")
    print("=" * 78)

    # Always-on: hold the carry continuously (collect + pay funding).
    show("always-on", run_carry(funding, args.capital, CarryConfig(always_on=True)))
    # Selective: only hold while funding is positive (skip/avoid paying).
    show("selective (rate>0)", run_carry(funding, args.capital,
                                         CarryConfig(entry_threshold=0.0, exit_threshold=0.0)))
    # Selective with a higher bar: only harvest richer funding.
    show("selective (rate>0.5bp)", run_carry(funding, args.capital,
                                             CarryConfig(entry_threshold=0.00005, exit_threshold=0.0)))
    print("=" * 78)
    print("  Note: assumes delta-neutral (price PnL ~0); returns are the funding")
    print("  carry net of round-trip fees on both legs. Modest by design -- low drawdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
