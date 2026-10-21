#!/usr/bin/env python3
"""How fast does a FundedNext Stellar 2-Step attempt pay, and what does speed cost?

Same book, data, costs and calibrated intraday check as scripts/fx_venue_compare.py.
Two questions:
  1. TIME: distribution of days to pass both phases, and to the first payout
     (21 days after funding). Trading days are converted to calendar days x7/5.
  2. SPEED vs ODDS: running the challenge at higher volatility reaches the
     target sooner but breaches more often. The fee is one-time and there is
     no time limit, so speed costs odds -- this measures how much.
Plus account size: payouts scale with the account, fees do not quite.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.fx_venue_compare as fv                         # noqa: E402
from scripts.fundednext_fx_ev import day_series               # noqa: E402

CAL_DAYS = 7 / 5
# Stellar 2-Step one-time prices (fundednext.com, read 2026-10-21) +10% swap-free
PRICES = {6_000: 39.99, 15_000: 119.99, 25_000: 199.99, 50_000: 299.99,
          100_000: 549.99, 200_000: 1_099.99}


def simulate(net, worst, v_ch, v_fd=0.06, n_paths=2500, seed=31):
    base = net.std() * np.sqrt(252)
    rng = np.random.default_rng(seed)
    n = len(net)

    def draw(m):
        out, i = [], rng.integers(n)
        while len(out) < m:
            out.append(i)
            i = rng.integers(n) if rng.random() < .1 else (i + 1) % n
        return out

    def phase(target, s):
        eq = 1.0
        for d, j in enumerate(draw(756), 1):
            if eq * (1 + worst[j] * s) <= max(.90, eq - .05):
                return None
            eq *= 1 + net[j] * s
            if eq - 1 >= target and d >= 5:
                return d
        return None

    def funded(s):
        eq, paid, warn, rs, cyc, nxt = 1.0, 0.0, 0, 1.0, 0.0, 21
        for d, j in enumerate(draw(504), 1):
            ss = s * rs
            lo = eq * (1 + worst[j] * ss)
            if lo <= max(.90, eq - .05):
                return paid
            if (eq - lo) > .03 * rs:
                warn += 1
                cyc = 0.0
                if warn >= 2:
                    rs = 1 / 3
            b = eq
            eq *= 1 + net[j] * ss
            cyc += eq - b
            if d >= nxt:
                take = max(0.0, min(eq - 1.02, cyc))
                if take > 0:
                    paid += take * .8
                    eq -= take
                cyc, nxt = 0.0, d + 14
        return paid

    sc, sf = v_ch / base, v_fd / base
    days, paid = [], []
    for _ in range(n_paths):
        d1 = phase(.08, sc)
        if d1 is None:
            continue
        d2 = phase(.05, sc)
        if d2 is None:
            continue
        days.append((d1 + d2) * CAL_DAYS)
        paid.append(funded(sf))           # as a fraction of account size
    return len(days) / n_paths, np.array(days), np.array(paid)


def main() -> int:
    net, worst = day_series(0.35)          # FundedNext $3/lot, blended
    worst = np.minimum(net, worst * fv.CAL)

    print("\n1. TIME TO GET PAID -- $100k, challenge at 8% vol (the ticket default)")
    pr, days, paid = simulate(net, worst, 0.08)
    q = np.percentile(days, [10, 25, 50, 75, 90])
    print(f"   pass rate {pr*100:.0f}%. Of the attempts that pass, calendar days to funded:")
    print(f"   fastest 10%: {q[0]:.0f}   25%: {q[1]:.0f}   median: {q[2]:.0f}"
          f"   75%: {q[3]:.0f}   slowest 10%: {q[4]:.0f}")
    print(f"   first payout = funded + 21 days -> median about {q[2]+21:.0f} days"
          f" (~{(q[2]+21)/30.4:.1f} months)")
    for m in (3, 6, 12):
        print(f"   chance an attempt is funded within {m:>2} months: "
              f"{pr * (days <= m*30.4).mean()*100:4.1f}%")

    print("\n2. SPEED vs ODDS -- challenge vol (funded at 6% in every case), $100k")
    print(f"   {'vol':>4} {'pass':>6} {'median days':>12} {'funded <6mo':>12} {'EV':>8}")
    for v in (0.06, 0.08, 0.10, 0.12, 0.15):
        pr, days, paid = simulate(net, worst, v)
        ev = pr * paid.mean() * 100_000 - 549.99 * 1.1
        print(f"   {v*100:3.0f}% {pr*100:5.1f}% {np.median(days):>12.0f}"
              f" {pr*(days <= 182).mean()*100:>11.1f}% ${ev:>7,.0f}")

    print("\n3. ACCOUNT SIZE -- same strategy, challenge 8%, funded 6%")
    pr, days, paid = simulate(net, worst, 0.08)
    print(f"   {'size':>9} {'price (swap-free)':>18} {'EV':>8} {'EV / price':>11}  note")
    for size, price in PRICES.items():
        fee = price * 1.1
        ev = pr * paid.mean() * size - fee
        note = "EAs allowed (bot can trade)" if size < 50_000 else "manual ticket only"
        if size <= 15_000:
            note += "; lot rounding coarse"
        print(f"   ${size:>8,} ${fee:>17,.2f} ${ev:>7,.0f} {ev/fee*100:>10.0f}%  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
