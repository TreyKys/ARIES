"""One audited profit-and-loss ledger. Every strategy must route through this.

Why this module exists. Three strategies in this repo reported profits that did
not exist, each from its own hand-written P&L arithmetic: the hedged grid booked
one leg and not the other; the all-perp variant inherited that; the calendar
spread leaked a roll artifact into the next day. The strategy logic was never
the problem -- the MEASUREMENT was, and it was re-implemented from scratch every
time.

The fix is structural, not vigilance. This ledger holds cash and positions, and
equity is ALWAYS cash + sum(position * price). There is no code path that adds
"profit" directly. A strategy therefore cannot book a gain it did not earn by
holding a position through a price change, because booking a gain is not an
operation this class offers.

The identity it enforces, checked in tests:

    between two marks, with no trades and no carry:
        d(equity) == sum over instruments of position_i * d(price_i)

Everything else -- fees, funding, swap, roll costs -- moves CASH explicitly and
is reported separately, so it can never masquerade as price P&L.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Fill:
    ts: int
    instrument: str
    qty: float          # +buy / -sell, in units
    price: float
    cost: float         # cash paid in fees/slippage (always >= 0)


class Ledger:
    """Cash + positions. Equity is derived, never assigned."""

    def __init__(self, capital: float):
        if capital <= 0:
            raise ValueError("capital must be positive")
        self.capital = float(capital)
        self.cash = float(capital)
        self.pos: Dict[str, float] = {}
        self.last_px: Dict[str, float] = {}
        self.fees_paid = 0.0
        self.carry_received = 0.0
        self.fills: List[Fill] = []
        self._peak = float(capital)
        self._max_dd = 0.0
        self.curve: List[Tuple[int, float]] = []

    # --- the only three ways anything changes -------------------------------

    def trade(self, ts: int, instrument: str, qty: float, price: float,
              cost: float = 0.0) -> None:
        """Buy/sell `qty` units at `price`, paying `cost` in cash.

        Cash falls by qty*price (buying converts cash into position) and by the
        cost. No profit is recognised here: profit appears only when `mark`
        revalues the position at a new price.
        """
        if cost < 0:
            raise ValueError("cost must be >= 0")
        if price <= 0 and instrument not in self.last_px:
            # negative/zero prices are legal for some futures (Apr 2020 WTI),
            # but a first mark at <=0 means the feed is wrong.
            raise ValueError(f"first price for {instrument} must be > 0")
        self.pos[instrument] = self.pos.get(instrument, 0.0) + qty
        self.cash -= qty * price + cost
        self.fees_paid += cost
        self.last_px[instrument] = price
        self.fills.append(Fill(ts, instrument, qty, price, cost))

    def accrue(self, amount: float, *, label: str = "carry") -> None:
        """Move cash for a non-price reason: funding, swap, interest, roll fee.

        Positive = received. Tracked apart from price P&L so a carry credit can
        never be mistaken for an oscillation profit -- the exact confusion that
        made the hedged grid look profitable.
        """
        self.cash += amount
        self.carry_received += amount

    def mark(self, ts: int, prices: Dict[str, float]) -> float:
        """Revalue every position at `prices` and return equity."""
        for k, v in prices.items():
            self.last_px[k] = v
        eq = self.equity()
        self._peak = max(self._peak, eq)
        if self._peak > 0:
            self._max_dd = max(self._max_dd, (self._peak - eq) / self._peak)
        self.curve.append((ts, eq))
        return eq

    # --- derived quantities -------------------------------------------------

    def equity(self) -> float:
        v = self.cash
        for k, q in self.pos.items():
            if q:
                v += q * self.last_px[k]
        return v

    def gross_exposure(self) -> float:
        return sum(abs(q) * self.last_px[k] for k, q in self.pos.items() if q)

    def net_exposure(self) -> float:
        return sum(q * self.last_px[k] for k, q in self.pos.items() if q)

    @property
    def max_drawdown_pct(self) -> float:
        return self._max_dd * 100.0

    def flatten(self, ts: int, prices: Dict[str, float], cost_rate: float = 0.0) -> None:
        """Close every position at `prices`, paying proportional cost."""
        for k in list(self.pos):
            q = self.pos[k]
            if q:
                p = prices.get(k, self.last_px[k])
                self.trade(ts, k, -q, p, cost=abs(q) * p * cost_rate)


@dataclass
class Stats:
    ann_return_pct: float
    ann_vol_pct: float
    sharpe: float
    max_drawdown_pct: float
    years: float
    sharpe_stderr: float
    sharpe_t: float
    final_equity: float
    fees_paid: float
    carry_received: float

    def __str__(self) -> str:
        return (f"ret {self.ann_return_pct:+6.2f}%/yr  vol {self.ann_vol_pct:5.2f}%  "
                f"Sharpe {self.sharpe:+5.2f} +/-{self.sharpe_stderr:.2f} "
                f"(t={self.sharpe_t:+.2f})  maxDD {self.max_drawdown_pct:5.2f}%  "
                f"{self.years:.1f}yr")


def summarise(led: Ledger, periods_per_year: int = 252) -> Stats:
    """Stats from the ledger's own equity curve, with Sharpe UNCERTAINTY.

    The standard error matters as much as the estimate: Sharpe error depends on
    elapsed YEARS, not on the number of bars, so a year of hourly data is just
    as uninformative as a year of daily data. Reporting Sharpe without its
    error is how a noise-level result gets mistaken for an edge.
    """
    import numpy as np
    if len(led.curve) < 3:
        return Stats(0, 0, 0, led.max_drawdown_pct, 0, float("inf"), 0,
                     led.equity(), led.fees_paid, led.carry_received)
    eq = np.array([e for _, e in led.curve], dtype=float)
    ts = np.array([t for t, _ in led.curve], dtype=float)
    r = np.diff(eq) / eq[:-1]
    r = r[np.isfinite(r)]
    span_days = (ts[-1] - ts[0]) / 86_400_000
    years = span_days / 365.25 if span_days > 0 else len(r) / periods_per_year
    ann = ((eq[-1] / eq[0]) ** (1 / years) - 1) * 100 if years > 0 and eq[-1] > 0 else -100.0
    vol = r.std(ddof=1) * np.sqrt(periods_per_year) * 100 if len(r) > 1 else 0.0
    sh = (r.mean() * periods_per_year) / (r.std(ddof=1) * np.sqrt(periods_per_year)) \
        if len(r) > 1 and r.std(ddof=1) > 0 else 0.0
    se = np.sqrt((1 + sh ** 2 / 2) / years) if years > 0 else float("inf")
    return Stats(ann, vol, sh, led.max_drawdown_pct, years, se,
                 sh / se if se > 0 else 0.0, eq[-1], led.fees_paid,
                 led.carry_received)
