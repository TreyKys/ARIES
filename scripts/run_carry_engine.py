#!/usr/bin/env python3
"""Run the multi-pair carry engine.

Replay real funding history (works anywhere, proves the engine):
    python scripts/fetch_funding.py ETHUSDT 2024-01 2025-06
    python scripts/fetch_funding.py SOLUSDT 2024-01 2025-06
    python scripts/fetch_funding.py LINKUSDT 2024-01 2025-06
    python scripts/run_carry_engine.py --replay --pairs ETHUSDT,SOLUSDT,LINKUSDT \
        --leverage 2 --capital 50

Live on the VPS polls funding every interval (needs exchange reachable):
    python scripts/run_carry_engine.py --live --pairs ETHUSDT,SOLUSDT,LINKUSDT --leverage 2
"""
import argparse
import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares.carry_engine import CarryEngine, CarryEngineConfig, merge_funding
from ares.reporting import ConsoleReporter

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def load_funding(pair: str):
    rows = []
    with open(f"data/{pair}_funding.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["ts"]), float(r["interval_hours"]), float(r["rate"])))
    rows.sort(key=lambda x: x[0])
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--pairs", default="ETHUSDT,SOLUSDT,LINKUSDT")
    p.add_argument("--leverage", type=float, default=2.0)
    p.add_argument("--capital", type=float, default=50.0)
    args = p.parse_args()
    pairs = [s.strip() for s in args.pairs.split(",")]

    if not args.replay:
        print("Live mode needs a reachable exchange (run on the VPS). "
              "Use --replay here to validate on real history.", file=sys.stderr)
        return 2

    streams = {pair: load_funding(pair) for pair in pairs}
    events = merge_funding(streams)
    days = (events[-1][0] - events[0][0]) / 86_400_000

    engine = CarryEngine(pairs, starting_capital=args.capital,
                         cfg=CarryEngineConfig(leverage=args.leverage),
                         reporter=ConsoleReporter())
    for ts, pair, rate in events:
        engine.on_funding(pair, ts, rate)

    s = engine.summary(days)
    print("=" * 70)
    print(f"  CARRY ENGINE  |  {', '.join(pairs)}  |  {args.leverage:g}x  |  "
          f"${args.capital:.0f}  |  {days:.0f} days")
    print("=" * 70)
    print(f"  Final equity ....... ${s['final_equity']:.2f}")
    print(f"  Total return ....... {s['total_return_pct']:+.1f}%")
    print(f"  Annualized ......... {s['annualized_pct']:+.1f}%")
    print(f"  Max drawdown ....... {s['max_drawdown_pct']:.2f}%")
    print(f"  Per-pair funding $ .. {s['per_pair']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
