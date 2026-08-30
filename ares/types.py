"""Shared, typed data structures for the ARES core.

Deliberately small and immutable-ish. One definition of each concept, so
there is never a second ``Candle`` class to disagree with the first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        """+1 for LONG, -1 for SHORT. Handy for PnL/level math."""
        return 1 if self is Side.LONG else -1


@dataclass(frozen=True)
class Candle:
    ts: int  # epoch milliseconds, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class StrategyDecision:
    """What a strategy wants to do. Prices are absolute, not distances."""
    side: Side
    stop_price: float
    take_profit_price: float
    reason: str
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    size: float = 0.0            # position size in base units
    risk_amount: float = 0.0     # intended dollar risk (1R) for this trade
    reason: str = ""


@dataclass
class Position:
    symbol: str
    side: Side
    size: float
    entry_price: float
    stop_price: float
    take_profit_price: float
    entry_ts: int
    risk_amount: float           # intended 1R in dollars, for R-multiple reporting
    entry_fee: float = 0.0


@dataclass
class Trade:
    symbol: str
    side: Side
    size: float
    entry_price: float
    exit_price: float
    entry_ts: int
    exit_ts: int
    pnl: float                   # net of fees
    fees: float
    r_multiple: float
    reason_open: str
    reason_close: str


@dataclass(frozen=True)
class Costs:
    """Fee/slippage model. Rates are fractions (0.0005 == 5 bps == 0.05%)."""
    taker_fee: float = 0.0005
    maker_fee: float = 0.0002
    slippage: float = 0.0005

    def entry_fill(self, ref_price: float, side: Side) -> float:
        """Market entry crosses the spread against you."""
        return ref_price * (1 + side.sign * self.slippage)

    def stop_fill(self, stop_price: float, side: Side) -> float:
        """Stop-outs slip further against you than the stop level."""
        return stop_price * (1 - side.sign * self.slippage)
