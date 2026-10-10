#!/usr/bin/env python3
"""Can the combined book survive a prop firm's rules? Measure, don't guess.

The user's goal was always a prop firm: trade someone else's capital. The
obstacle was never the edge, it was that the book HOLDS OVERNIGHT and almost
every futures prop firm force-liquidates before the daily close. Research
(docs/PROP_FIRMS.md) found exactly one firm whose published rules permit
overnight AND weekend holds on a funded account: Phidias Premium.

So the question becomes arithmetic rather than policy: with a $3,000 end-of-day
trailing drawdown on a $100,000 account, what are the odds of passing the
$6,000 evaluation, and what does the funded account pay per month afterwards?

Method. Take the strategy's REAL daily returns from the 26-year replay, scale
them to a chosen volatility, and bootstrap forward through the firm's actual
rules. Block bootstrap, not iid: daily returns here are mildly autocorrelated
and drawdown depends almost entirely on how losses cluster, so resampling one
day at a time would understate the risk that matters.

Everything the firm charges is counted: the evaluation fee, the activation
fee, the profit split, the payout cap, and the rule that a trading day only
counts toward a payout cycle if it cleared a minimum profit.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.INFO)

from run_aries_futures import run_replay            # noqa: E402

TRADING_DAYS = 252


@dataclass(frozen=True)
class Rules:
    """A prop firm's published terms. All figures in account currency."""
    name: str
    size: float                  # nominal account size
    drawdown: float              # end-of-day trailing drawdown
    dd_locks_at: float           # floor stops trailing here (funded); inf = never
    profit_target: float         # evaluation target profit
    min_days: int                # minimum evaluation trading days
    payout_every: int            # qualifying trading days between payouts
    payout_min_day_pnl: float    # a day counts only if it cleared this
    payout_cap: float            # maximum per payout cycle
    payout_threshold: float      # equity needed before any withdrawal
    payout_floor: float          # balance may not fall below this after one
    eval_fee: float
    activation_fee: float
    splits: tuple                # trader's share, payout by payout


# Phidias Premium, from the firm's own rules page, verified 2026-10-09.
# The one published rule set that allows overnight AND weekend holds.
PHIDIAS_100K = Rules(
    name="Phidias Premium 100K", size=100_000.0, drawdown=3_000.0,
    dd_locks_at=100_100.0, profit_target=6_000.0, min_days=1,
    payout_every=5, payout_min_day_pnl=200.0, payout_cap=2_500.0,
    payout_threshold=103_700.0, payout_floor=100_100.0,
    eval_fee=450.0, activation_fee=149.0,
    splits=(0.75, 0.80, 0.85, 0.90, 1.00))

PHIDIAS_50K = Rules(
    name="Phidias Premium 50K", size=50_000.0, drawdown=2_500.0,
    dd_locks_at=50_100.0, profit_target=4_000.0, min_days=1,
    payout_every=5, payout_min_day_pnl=150.0, payout_cap=2_000.0,
    payout_threshold=52_600.0, payout_floor=50_100.0,
    eval_fee=350.0, activation_fee=149.0,
    splits=(0.75, 0.80, 0.85, 0.90, 1.00))

PHIDIAS_150K = Rules(
    name="Phidias Premium 150K", size=150_000.0, drawdown=4_500.0,
    # The rules page does not state the 150K funded lock level; the other two
    # sizes lock at size + 100, so assume the same and flag it.
    dd_locks_at=150_100.0, profit_target=9_000.0, min_days=1,
    payout_every=5, payout_min_day_pnl=250.0, payout_cap=2_750.0,
    payout_threshold=154_500.0, payout_floor=150_100.0,
    eval_fee=550.0, activation_fee=169.0,
    splits=(0.75, 0.80, 0.85, 0.90, 1.00))


def strategy_daily_returns(capital: float = 25_000.0,
                           w_trend: float = 0.5) -> np.ndarray:
    """The replay's own daily returns. The ledger is the only source."""
    led = run_replay(capital, target_vol=0.03, w_trend=w_trend, top_k=3,
                     monitor=False)
    eq = np.array([e for _, e in led.curve], dtype=float)
    r = np.diff(eq) / eq[:-1]
    return r[np.isfinite(r)]


def block_bootstrap(r: np.ndarray, n: int, rng, mean_block: int = 10
                    ) -> np.ndarray:
    """Stationary bootstrap: geometric blocks, wrapping at the end.

    Losses cluster, and a drawdown limit is a bet on exactly that clustering.
    Resampling single days would break it up and make every rule look easier
    to survive than it is.
    """
    out = np.empty(n)
    i = 0
    p = 1.0 / mean_block
    idx = rng.integers(len(r))
    while i < n:
        out[i] = r[idx]
        i += 1
        idx = (rng.integers(len(r)) if rng.random() < p
               else (idx + 1) % len(r))
    return out


def run_eval(path: np.ndarray, k: Rules) -> tuple:
    """(passed, day_index). The floor trails EOD and never locks in eval."""
    eq = k.size
    hwm = k.size
    for d, ret in enumerate(path, start=1):
        eq *= (1.0 + ret)
        if eq > hwm:
            hwm = eq
        if eq <= hwm - k.drawdown:
            return False, d
        if eq - k.size >= k.profit_target and d >= k.min_days:
            return True, d
    return False, len(path)


def run_funded(path: np.ndarray, k: Rules, buffer: float = 0.0) -> tuple:
    """(gross_paid_out, survived_days, breached).

    Models the three funded rules that actually bind: the floor that stops
    trailing once it reaches the account size, the payout cycle that only
    counts days clearing a minimum profit, and the cap on each payout.

    `buffer` is how much equity the trader leaves ABOVE the floor when
    withdrawing. It is not a firm rule, it is the single most important
    decision the trader makes: the firm permits withdrawing down to the floor
    exactly, and doing so leaves the account one bad day from a breach.
    """
    eq = k.size
    hwm = k.size
    paid = 0.0
    qualifying = 0
    payouts = 0
    for d, ret in enumerate(path, start=1):
        before = eq
        eq *= (1.0 + ret)
        if eq > hwm:
            hwm = eq
        floor = min(hwm - k.drawdown, k.dd_locks_at)
        if eq <= floor:
            return paid, d, True
        if eq - before >= k.payout_min_day_pnl:
            qualifying += 1
        if qualifying >= k.payout_every and eq >= k.payout_threshold:
            take = min(k.payout_cap, eq - (k.payout_floor + buffer))
            if take >= 500.0:                      # firm's minimum withdrawal
                share = k.splits[min(payouts, len(k.splits) - 1)]
                paid += take * share
                eq -= take
                payouts += 1
                qualifying = 0
    return paid, len(path), False


def study(r: np.ndarray, k: Rules, vol_targets, horizon_days: int,
          paths: int, seed: int = 7, buffer: float = 0.0) -> None:
    base_vol = r.std() * np.sqrt(TRADING_DAYS)
    rng = np.random.default_rng(seed)
    print(f"\n=== {k.name} | withdrawal buffer ${buffer:,.0f} ===")
    print(f"  drawdown ${k.drawdown:,.0f} EOD trailing, locks at "
          f"${k.dd_locks_at:,.0f} | target ${k.profit_target:,.0f}")
    print(f"  strategy base vol {base_vol*100:.2f}%/yr, "
          f"Sharpe {r.mean()/r.std()*np.sqrt(TRADING_DAYS):+.2f}")
    print(f"\n  {'vol':>6} {'ret/yr':>7} {'pass eval':>10} {'med days':>9}"
          f" {'breach 1y':>10} {'paid/yr':>9} {'$/month':>9} {'EV net':>9}")
    print("  " + "-" * 76)
    for vt in vol_targets:
        scale = vt / base_vol
        rs = r * scale
        passed = []
        days = []
        paid = []
        breached = []
        for _ in range(paths):
            p = block_bootstrap(rs, horizon_days * 2, rng)
            ok, d = run_eval(p[:horizon_days], k)
            passed.append(ok)
            if ok:
                days.append(d)
                got, _, br = run_funded(p[d:d + horizon_days], k, buffer)
                paid.append(got)
                breached.append(br)
        pr = float(np.mean(passed))
        md = float(np.median(days)) if days else float("nan")
        bp = float(np.mean(breached)) if breached else float("nan")
        mp = float(np.mean(paid)) if paid else 0.0
        # Expected value to the trader: payouts only happen if the evaluation
        # is passed, but the fees are paid either way.
        ev = pr * mp - (k.eval_fee + pr * k.activation_fee)
        print(f"  {vt*100:5.1f}% {vt*100*(r.mean()/r.std()*np.sqrt(TRADING_DAYS)):6.1f}%"
              f" {pr*100:9.1f}% {md:9.0f} {bp*100:9.1f}%"
              f" ${mp:8,.0f} ${mp/12:8,.0f} ${ev:8,.0f}")


def required_sharpe(k: Rules, paths: int, horizon_days: int,
                    seed: int = 11) -> None:
    """What quality of strategy DOES clear this gate?

    The measured book fails, so the useful question is what would not. This
    sweeps synthetic Gaussian return streams by Sharpe, holding the firm's
    rules fixed, which turns "no" into a number to aim at.
    """
    rng = np.random.default_rng(seed)
    print(f"\n=== what Sharpe clears {k.name}? ===")
    print(f"  {'Sharpe':>7} {'vol':>6} {'ret/yr':>7} {'pass':>7}"
          f" {'breach 1y':>10} {'$/month':>9} {'EV/attempt':>11}")
    print("  " + "-" * 64)
    for sharpe in (0.4, 0.8, 1.2, 1.6, 2.0, 3.0):
        best = None
        for vt in (0.03, 0.05, 0.08, 0.12, 0.18, 0.25):
            mu = sharpe * vt / TRADING_DAYS
            sd = vt / np.sqrt(TRADING_DAYS)
            passed, paid, breached = [], [], []
            for _ in range(paths):
                p_ = rng.normal(mu, sd, horizon_days * 2)
                ok, d = run_eval(p_[:horizon_days], k)
                passed.append(ok)
                if ok:
                    got, _, br = run_funded(p_[d:d + horizon_days], k, 1_000.0)
                    paid.append(got)
                    breached.append(br)
            pr = float(np.mean(passed))
            mp = float(np.mean(paid)) if paid else 0.0
            ev = pr * mp - (k.eval_fee + pr * k.activation_fee)
            row = (ev, sharpe, vt, sharpe * vt, pr,
                   float(np.mean(breached)) if breached else float("nan"), mp)
            if best is None or ev > best[0]:
                best = row
        _, sh, vt, ret, pr, bp, mp = best
        print(f"  {sh:7.1f} {vt*100:5.1f}% {ret*100:6.1f}% {pr*100:6.1f}%"
              f" {bp*100:9.1f}% ${mp/12:8,.0f} ${best[0]:10,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=2000)
    ap.add_argument("--horizon", type=int, default=252)
    ap.add_argument("--w-trend", type=float, default=0.5,
                    help="0.0 = reversal only, the book after dropping the "
                         "trend leg")
    a = ap.parse_args()
    r = strategy_daily_returns(w_trend=a.w_trend)
    print(f"strategy: {len(r)} daily returns, "
          f"{len(r)/TRADING_DAYS:.1f} years of them")
    # Does a LONGER evaluation at lower volatility help? Phidias sets a
    # minimum of 1 trading day and no stated maximum, so patience is a lever
    # worth testing before concluding.
    print("\n--- evaluation with no deadline (5 years allowed) ---")
    study(r, PHIDIAS_100K, [0.02, 0.03, 0.05, 0.08], 1260, a.paths // 3,
          buffer=1_000.0)
    print("\n--- evaluation inside one year ---")
    study(r, PHIDIAS_100K, [0.03, 0.05, 0.08, 0.12, 0.18, 0.25], 252,
          a.paths, buffer=1_000.0)
    required_sharpe(PHIDIAS_100K, a.paths // 2, 252)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
