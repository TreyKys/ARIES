#!/usr/bin/env python3
"""Measure the edge in: long dated quarterly + short perp (one account, no spot).

Mechanics. A dated future pays no funding; the perp does. Holding the quarterly
long and the perp short is delta-neutral, so the short leg's funding is income.
But the quarterly carries its own premium over the perp, and that premium
converges to zero at expiry -- which, held long, is a cost. So:

    net edge ~= annualised funding collected  -  annualised quarterly premium

Both legs are derivatives, so this fits a single prop account. The question is
purely whether the first term exceeds the second.
"""
import csv, sys
from datetime import datetime, timezone
from pathlib import Path


def rd(path, col="close"):
    with open(path) as f:
        return {int(r["ts"]): float(r[col]) for r in csv.DictReader(f)}


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    perp = rd(f"data/{base}_perp_1h.csv")
    with open(f"data/funding/{base}.csv") as f:
        fund = [(int(r["calc_time"]), float(r["last_funding_rate"]))
                for r in csv.DictReader(f)]
    files = sorted(Path("data/quarterly").glob(f"{base}_*.csv"))
    if not files:
        print("no quarterly files yet", file=sys.stderr); return 1
    print(f"{base}: long quarterly / short perp, per contract")
    print(f"{'contract':18s}{'days':>6s}{'ann basis':>11s}{'ann funding':>13s}"
          f"{'EDGE':>9s}")
    print("-" * 57)
    tot_edge, n = 0.0, 0
    for p in files:
        exp = p.stem.split("_")[1]
        q = rd(p)
        ts = sorted(set(q) & set(perp))
        if len(ts) < 200:
            continue
        # expiry at 08:00 UTC on the dated day
        ed = datetime(2000 + int(exp[:2]), int(exp[2:4]), int(exp[4:6]),
                      8, tzinfo=timezone.utc).timestamp() * 1000
        # average annualised premium over the contract's traded life
        prem, cnt = 0.0, 0
        for t in ts:
            days = (ed - t) / 86_400_000
            if days < 3 or days > 365:
                continue
            prem += (q[t] / perp[t] - 1.0) * 365.0 / days
            cnt += 1
        if not cnt:
            continue
        ann_basis = prem / cnt * 100
        lo, hi = ts[0], ts[-1]
        fr = [r for tt, r in fund if lo <= tt <= hi]
        if not fr:
            continue
        ann_fund = sum(fr) / len(fr) * 3 * 365 * 100
        edge = ann_fund - ann_basis
        tot_edge += edge; n += 1
        print(f"{p.stem:18s}{(hi-lo)/86400000:6.0f}{ann_basis:+10.2f}%"
              f"{ann_fund:+12.2f}%{edge:+8.2f}%")
    if n:
        print("-" * 57)
        print(f"{'MEAN':18s}{'':6s}{'':11s}{'':13s}{tot_edge/n:+8.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
