"""Deterministic risk management: position sizing and hard gates.

Sizing is genuinely risk-based -- size = (equity * risk%) / stop_distance --
so every trade risks the same fraction of the account regardless of price
or volatility. This is the rule the whole ARES spec is built on, and the
place the old engine got wrong (it sized a fixed notional * 10x leverage).

All functions are pure: state (equity, drawdown, streak) is passed in, so
the same inputs always yield the same decision.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .types import RiskDecision, StrategyDecision


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.015        # 1.5% of equity risked per trade
    reduced_risk: float = 0.005          # after a losing streak
    consec_loss_threshold: int = 2       # losses before risk is throttled
    max_total_drawdown: float = 0.10     # halt new trades past 10% from peak
    max_daily_drawdown: float = 0.04     # halt new trades past 4% loss on the day
    max_position_leverage: float = 5.0   # notional cannot exceed equity * this
    min_notional: float = 5.0            # exchange minimum order value (USDT)
    qty_step: float = 0.001              # round size down to this increment


@dataclass(frozen=True)
class AccountState:
    equity: float
    peak_equity: float
    day_start_equity: float
    day_pnl: float
    consecutive_losses: int


def _round_down(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def evaluate(
    account: AccountState,
    decision: StrategyDecision,
    entry_price: float,
    cfg: RiskConfig,
) -> RiskDecision:
    # 1. Total drawdown halt
    if account.peak_equity > 0:
        total_dd = (account.peak_equity - account.equity) / account.peak_equity
        if total_dd >= cfg.max_total_drawdown:
            return RiskDecision(False, reason=f"Total drawdown halt ({total_dd:.1%})")

    # 2. Daily loss halt
    if account.day_start_equity > 0:
        day_loss = -account.day_pnl / account.day_start_equity
        if day_loss >= cfg.max_daily_drawdown:
            return RiskDecision(False, reason=f"Daily loss limit hit ({day_loss:.1%})")

    # 3. Adaptive risk fraction after a losing streak
    risk_pct = (cfg.reduced_risk
                if account.consecutive_losses >= cfg.consec_loss_threshold
                else cfg.risk_per_trade)

    stop_dist = abs(entry_price - decision.stop_price)
    if stop_dist <= 0:
        return RiskDecision(False, reason="Non-positive stop distance")

    risk_amount = account.equity * risk_pct
    size = risk_amount / stop_dist

    # 4. Cap notional by max leverage (reduces size -> risks less, never more)
    notional = size * entry_price
    max_notional = account.equity * cfg.max_position_leverage
    if notional > max_notional:
        size = max_notional / entry_price
        notional = size * entry_price
        risk_amount = size * stop_dist

    # 5. Round size down to the exchange increment
    size = _round_down(size, cfg.qty_step)
    notional = size * entry_price
    risk_amount = size * stop_dist

    # 6. Reject sub-minimum orders (real constraint on a $50 account)
    if size <= 0 or notional < cfg.min_notional:
        return RiskDecision(
            False,
            reason=f"Order below exchange minimum (${notional:.2f} < ${cfg.min_notional:.2f})",
        )

    return RiskDecision(True, size=size, risk_amount=risk_amount,
                        reason=f"Risking ${risk_amount:.2f} ({risk_pct:.2%})")
