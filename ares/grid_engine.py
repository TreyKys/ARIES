"""Live hedged-grid engine (event-driven, paper-capable).

The deployable version of the delta-neutral grid: feed it candles via
step(); it maintains long spot inventory + a short perp hedge, harvests the
oscillations, and reports true state to a Reporter. Same math as
ares.grid.backtest_hedged_grid, restructured for live/paper use.

PAPER mode simulates fills against the real price. A future LIVE mode swaps
in a real two-leg broker behind the identical logic. No price prediction,
no leverage beyond the hedge itself.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Optional

from .reporting import ConsoleReporter, Reporter
from .types import Candle


class HedgedGridEngine:
    def __init__(self, symbol: str, *, capital: float = 50.0,
                 atr_period: int = 48, atr_mult: float = 0.5,
                 max_inventory: int = 20, maker_fee: float = 0.0002,
                 taker_fee: float = 0.0005, funding_8h: float = 0.0001,
                 min_edge_mult: float = 2.0, reporter: Optional[Reporter] = None):
        self.symbol = symbol
        self.capital = capital
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.max_inventory = max_inventory
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.funding_8h = funding_8h
        self.min_spacing_frac = min_edge_mult * (2 * maker_fee + 2 * taker_fee)
        self.reporter = reporter or ConsoleReporter()

        self.unit = capital / max_inventory
        self._win: deque[Candle] = deque(maxlen=atr_period + 1)
        self.inventory: list[float] = []     # buy prices (FIFO)
        self.realized = 0.0
        self.round_trips = 0
        self.last: Optional[float] = None
        self.last_fund: Optional[int] = None
        self.peak = capital
        self.max_dd = 0.0

    def _atr(self) -> Optional[float]:
        if len(self._win) < self.atr_period + 1:
            return None
        trs = []
        prev = None
        for c in self._win:
            if prev is not None:
                trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
            prev = c
        return sum(trs) / len(trs) if trs else None

    def step(self, candle: Candle) -> None:
        self._win.append(candle)
        p = candle.close
        if self.last is None:
            self.last = p
            self.last_fund = candle.ts
        atr = self._atr()
        if atr is None:
            return
        sp = max(self.atr_mult * atr, self.min_spacing_frac * p)
        if sp <= 0:
            return

        # sell rungs as price steps up
        while self.inventory and p >= self.last + sp:
            bp = self.inventory.pop(0)
            sell = self.last + sp
            profit = (sell / bp - 1) * self.unit - 2 * self.maker_fee * self.unit - self.taker_fee * self.unit
            self.realized += profit
            self.round_trips += 1
            self.last += sp
            self.reporter.log("GRID", f"{self.symbol} sell rung @ {sell:.4f} "
                              f"(+${profit:.4f}, {self.round_trips} hits)", "SUCCESS")
        # buy rungs + hedge as price steps down
        while len(self.inventory) < self.max_inventory and p <= self.last - sp:
            self.last -= sp
            self.inventory.append(self.last)
            self.realized -= self.taker_fee * self.unit     # add one hedge unit
            self.reporter.log("GRID", f"{self.symbol} buy rung @ {self.last:.4f} "
                              f"(+short hedge, inv {len(self.inventory)})", "INFO")
        if not self.inventory:
            self.last = p

        # funding collected on the short hedge (~every 8h)
        if self.last_fund is not None and candle.ts - self.last_fund >= 8 * 3600 * 1000 and self.inventory:
            self.realized += self.funding_8h * self.unit * len(self.inventory)
            self.last_fund = candle.ts

        equity = self.capital + self.realized          # directional P&L hedged away
        self.peak = max(self.peak, equity)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, (self.peak - equity) / self.peak)
        self._publish(equity)

    def _publish(self, equity: float) -> None:
        pnl = equity - self.capital
        self.reporter.state(
            balance=round(equity, 4),
            today_pnl_abs=round(pnl, 4),
            today_pnl_pct=round(pnl / self.capital * 100, 3),
            win_rate=round(min(len(self.inventory) / self.max_inventory * 100, 100), 1),
            is_connected=True,
        )
