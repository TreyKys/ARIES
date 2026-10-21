#!/usr/bin/env python3
"""FX-majors reversal at FundedNext (swap-free) vs FTMO (swaps unknown),
with the intraday check CALIBRATED against real hourly paths.

The daily-OHLC bound (every leg at its worst price at once) is pessimistic.
Measured on 665 days of genuine hourly FX paths, the real portfolio's worst
intraday dip averages 29% of that bound and 46% in the worst 5% of days.
The tail ratio, 0.46, is used here: breaches happen in the tail, and the
hourly comparison understates true intra-hour extremes slightly, so this
remains on the conservative side.

FundedNext Stellar 2-Step: +8% / +5%, static 10%, 5% daily, funded open-risk
cap 3% (first breach forfeits the cycle, second cuts risk to 1%), payouts at
day 21 then every 14, 80%, $605 swap-free.
FTMO 2-Step Swing: +10% / +5%, static 10%, 5% daily, payouts every 14 days,
80%, $590 refunded with the first payout. FTMO is not swap-free; its FX swap
is a parameter.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fundednext_fx_ev import day_series            # noqa: E402

CAL = 0.46


def run(net, worst, vol, venue, n_paths=1500, horizon=504, seed=13):
    scale = vol / (net.std() * np.sqrt(252))
    rng = np.random.default_rng(seed)
    n = len(net)
    p1, fee, refund = (0.08, 605.0, False) if venue == "fn" else (0.10, 590.0, True)

    def draw(m):
        out, i = [], rng.integers(n)
        while len(out) < m:
            out.append(i)
            i = rng.integers(n) if rng.random() < 0.1 else (i + 1) % n
        return out

    def phase(target):
        eq = 1.0
        for d, j in enumerate(draw(horizon), 1):
            if eq * (1 + worst[j] * scale) <= max(0.90, eq - 0.05):
                return False, d
            eq *= 1 + net[j] * scale
            if eq - 1.0 >= target and d >= (5 if venue == "fn" else 1):
                return True, d
        return False, horizon

    def funded():
        eq, paid, warn, rs, cyc, nxt, first = 1.0, 0.0, 0, 1.0, 0.0, (21 if venue == "fn" else 14), False
        for d, j in enumerate(draw(horizon), 1):
            s = scale * rs
            lo = eq * (1 + worst[j] * s)
            if lo <= max(0.90, eq - 0.05):
                return paid, first
            if venue == "fn" and (eq - lo) > 0.03 * rs:
                warn += 1
                cyc = 0.0
                if warn >= 2:
                    rs = 1 / 3
            b = eq
            eq *= 1 + net[j] * s
            cyc += eq - b
            if d >= nxt:
                take = max(0.0, min(eq - 1.02, cyc if venue == "fn" else eq - 1.02))
                if take > 0:
                    paid += take * 0.80 * 100_000
                    eq -= take
                    first = True
                cyc, nxt = 0.0, d + 14
        return paid, first

    passes, val = 0, []
    for _ in range(n_paths):
        if not phase(p1)[0] or not phase(0.05)[0]:
            continue
        passes += 1
        paid, first = funded()
        val.append(paid + (fee if (refund and first) else 0.0))
    pr = passes / n_paths
    mv = float(np.mean(val)) if val else 0.0
    return pr, mv, pr * mv - fee


def main() -> int:
    print("\nFX-majors reversal, calibrated intraday check, 2 years per phase\n")
    print(f"  {'venue':22s} {'cost':>5} {'swap':>5} {'Sharpe':>7} {'vol':>4}"
          f" {'pass':>6} {'value if funded':>16} {'EV/attempt':>11}")
    for bp in (0.3, 0.5):
        net0, worst0 = day_series(bp)
        for venue, swaps in (("fn", (0.0,)), ("ftmo", (0.0, 0.01, 0.02))):
            for sw in swaps:
                drag = sw / 252 * 1.0                  # on 1x gross, per day
                net = net0 - drag
                worst = np.minimum(net, worst0 * CAL - drag)
                sh = net.mean() / net.std() * np.sqrt(252)
                for vol in (0.06, 0.08, 0.10):
                    pr, mv, ev = run(net, worst, vol, venue)
                    name = "FundedNext (swap-free)" if venue == "fn" else "FTMO 2-Step Swing"
                    print(f"  {name:22s} {bp:4.1f}bp {sw*100:4.0f}% {sh:>+7.2f} {vol*100:3.0f}%"
                          f" {pr*100:5.1f}% ${mv:>15,.0f} ${ev:>10,.0f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
