"""Delta-neutral funding-rate carry backtest.

Hold long spot + short perpetual (or vice-versa) so price risk cancels,
and collect the perpetual funding payment. Because the position is
market-neutral and low-turnover, transaction costs are a tiny, one-off
fraction of returns -- the opposite of the micro-scalping cost trap.

This is a pure function of the funding-rate series (same input -> same
output). Price/basis PnL is assumed ~0 (that is the point of delta
neutrality); the residual basis drift is small and is left as a documented
simplification, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class CarryConfig:
    taker_fee: float = 0.0005        # per leg, per side
    notional_mult: float = 1.0       # carry notional = capital * this (1x = delta-neutral pair)
    entry_threshold: float = 0.0     # enter only when funding rate > this (per interval)
    exit_threshold: float = 0.0      # exit when funding rate <= this
    always_on: bool = False          # ignore thresholds, always hold the carry


@dataclass
class CarryResult:
    metrics: dict
    equity_curve: List[Tuple[int, float]]
    final_equity: float
    starting_capital: float

    def summary(self) -> str:
        m = self.metrics
        return (f"intervals={m['intervals']} in_market={m['pct_in_market']:.0%}  "
                f"funding=${m['funding_collected']:.2f} fees=${m['fees']:.2f}  "
                f"return={m['total_return_pct']:+.1f}%  annualized={m['annualized_pct']:+.1f}%  "
                f"maxDD={m['max_drawdown_pct']:.2f}%")


def run_carry(funding: Sequence[Tuple[int, float, float]],
              starting_capital: float = 50.0,
              cfg: CarryConfig = CarryConfig()) -> CarryResult:
    """funding: list of (calc_time_ms, interval_hours, rate_per_interval)."""
    equity = starting_capital
    peak = equity
    in_market = False
    notional = starting_capital * cfg.notional_mult
    leg_cost = 2 * notional * cfg.taker_fee   # both legs, one side

    curve: List[Tuple[int, float]] = []
    collected = 0.0
    fees = 0.0
    n_in = 0
    max_dd = 0.0

    for ts, _hrs, rate in funding:
        want = cfg.always_on or (rate > cfg.entry_threshold)
        if in_market and not cfg.always_on and rate <= cfg.exit_threshold:
            want = False

        if want and not in_market:
            equity -= leg_cost; fees += leg_cost; in_market = True
        elif not want and in_market:
            equity -= leg_cost; fees += leg_cost; in_market = False

        if in_market:
            pnl = rate * notional         # short perp receives funding when rate > 0
            equity += pnl; collected += pnl; n_in += 1

        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
        curve.append((ts, equity))

    if in_market:
        equity -= leg_cost; fees += leg_cost

    n = len(funding)
    days = (funding[-1][0] - funding[0][0]) / 86_400_000 if n > 1 else 0
    total_return = (equity / starting_capital - 1.0) * 100.0
    annualized = ((equity / starting_capital) ** (365.0 / days) - 1.0) * 100.0 if days > 0 else 0.0

    metrics = {
        "intervals": n,
        "pct_in_market": (n_in / n) if n else 0.0,
        "funding_collected": collected,
        "fees": fees,
        "total_return_pct": total_return,
        "annualized_pct": annualized,
        "max_drawdown_pct": max_dd * 100.0,
        "days": days,
    }
    return CarryResult(metrics, curve, equity, starting_capital)
