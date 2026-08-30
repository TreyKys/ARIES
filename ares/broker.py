"""Paper broker: simulated fills against real prices, with realistic costs.

The backtester and the live paper-trading loop both drive this same
broker, so "what the backtest showed" and "what paper trading does" come
from identical fill logic. Fees and slippage are always deducted -- the
number one reason a high-frequency micro-account strategy that looks
profitable on paper bleeds out in reality.
"""
from __future__ import annotations

from typing import List, Optional

from .types import Candle, Costs, Position, Side, StrategyDecision, Trade


class PaperBroker:
    def __init__(self, starting_capital: float, costs: Optional[Costs] = None):
        self.starting_capital = starting_capital
        self.equity = starting_capital
        self.costs = costs or Costs()
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []

    # --- queries -----------------------------------------------------------
    @property
    def flat(self) -> bool:
        return self.position is None

    def unrealized(self, price: float) -> float:
        if self.position is None:
            return 0.0
        p = self.position
        return (price - p.entry_price) * p.size * p.side.sign

    def mark_to_market(self, price: float) -> float:
        return self.equity + self.unrealized(price)

    # --- actions -----------------------------------------------------------
    def open(self, symbol: str, decision: StrategyDecision, size: float,
             risk_amount: float, ref_price: float, ts: int) -> Position:
        if self.position is not None:
            raise RuntimeError("PaperBroker already holds a position")
        fill = self.costs.entry_fill(ref_price, decision.side)
        entry_fee = fill * size * self.costs.taker_fee
        # Fees are realised at close so that equity == start + sum(trade.pnl).
        self.position = Position(
            symbol=symbol, side=decision.side, size=size, entry_price=fill,
            stop_price=decision.stop_price, take_profit_price=decision.take_profit_price,
            entry_ts=ts, risk_amount=risk_amount, entry_fee=entry_fee,
        )
        return self.position

    def process(self, candle: Candle) -> Optional[Trade]:
        """Advance one candle. Closes the position if stop or target is touched."""
        if self.position is None:
            return None
        p = self.position

        exit_price: Optional[float] = None
        reason = ""
        if p.side is Side.LONG:
            if candle.low <= p.stop_price:                 # stop checked first (conservative)
                exit_price = self.costs.stop_fill(p.stop_price, p.side)
                reason = "stop"
            elif candle.high >= p.take_profit_price:
                exit_price = p.take_profit_price
                reason = "target"
        else:
            if candle.high >= p.stop_price:
                exit_price = self.costs.stop_fill(p.stop_price, p.side)
                reason = "stop"
            elif candle.low <= p.take_profit_price:
                exit_price = p.take_profit_price
                reason = "target"

        if exit_price is None:
            return None
        return self._close(exit_price, candle.ts, reason)

    def close_at(self, price: float, ts: int, reason: str = "manual") -> Optional[Trade]:
        if self.position is None:
            return None
        return self._close(price, ts, reason)

    def _close(self, exit_price: float, ts: int, reason: str) -> Trade:
        p = self.position
        exit_fee = exit_price * p.size * self.costs.taker_fee
        gross = (exit_price - p.entry_price) * p.size * p.side.sign
        pnl = gross - p.entry_fee - exit_fee     # net of both fees
        self.equity += pnl
        total_fees = p.entry_fee + exit_fee
        r_multiple = pnl / p.risk_amount if p.risk_amount > 0 else 0.0
        trade = Trade(
            symbol=p.symbol, side=p.side, size=p.size,
            entry_price=p.entry_price, exit_price=exit_price,
            entry_ts=p.entry_ts, exit_ts=ts,
            pnl=pnl, fees=total_fees, r_multiple=r_multiple,
            reason_open="", reason_close=reason,
        )
        self.trades.append(trade)
        self.position = None
        return trade
