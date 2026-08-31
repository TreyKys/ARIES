"""Multi-pair delta-neutral carry engine (the ARES core).

Runs one delta-neutral carry per pair (long spot + short perp, so price
cancels) and harvests funding, splitting capital across pairs and applying
a chosen leverage to the price-neutral position. Event-driven: feed it
funding events via ``on_funding`` (from a replay of history, or a live
8-hourly poll on the VPS). Publishes true portfolio state through a
Reporter.

Safety: an always-on carry bleeds during negative-funding stretches, so a
per-pair circuit breaker exits when funding is deeply negative and
re-enters when it recovers -- with hysteresis, so it does not churn fees
the way naive zero-crossing toggling did in testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .reporting import ConsoleReporter, Reporter


@dataclass
class CarryEngineConfig:
    leverage: float = 2.0
    taker_fee: float = 0.0005          # per leg, per side
    neg_funding_exit: float = -0.0003  # exit a pair if funding <= this (deeply negative)
    reenter_funding: float = 0.00005   # re-enter once funding recovers above this


@dataclass
class _PairState:
    notional: float
    in_market: bool = True
    equity_contrib: float = 0.0        # cumulative funding - fees for this pair


class CarryEngine:
    def __init__(self, pairs: Sequence[str], starting_capital: float = 50.0,
                 cfg: Optional[CarryEngineConfig] = None,
                 reporter: Optional[Reporter] = None):
        if not pairs:
            raise ValueError("need at least one pair")
        self.cfg = cfg or CarryEngineConfig()
        self.reporter = reporter or ConsoleReporter()
        self.starting_capital = starting_capital
        self.equity = starting_capital
        self.peak_equity = starting_capital
        self.max_dd = 0.0

        slice_capital = starting_capital / len(pairs)
        notional = slice_capital * self.cfg.leverage
        self.pairs: Dict[str, _PairState] = {
            p: _PairState(notional=notional) for p in pairs
        }
        self._leg_cost = 2 * notional * self.cfg.taker_fee  # both legs, one side

    def on_funding(self, pair: str, ts: int, rate: float) -> None:
        st = self.pairs.get(pair)
        if st is None:
            return

        # hysteresis circuit breaker (avoids fee churn around zero funding)
        if st.in_market and rate <= self.cfg.neg_funding_exit:
            self.equity -= self._leg_cost
            st.equity_contrib -= self._leg_cost
            st.in_market = False
            self.reporter.log("CARRY", f"{pair}: funding {rate:.4%} -> exit (deeply negative)", "WARN")
        elif not st.in_market and rate >= self.cfg.reenter_funding:
            self.equity -= self._leg_cost
            st.equity_contrib -= self._leg_cost
            st.in_market = True
            self.reporter.log("CARRY", f"{pair}: funding {rate:.4%} -> re-enter", "INFO")

        if st.in_market:
            pnl = rate * st.notional          # short perp receives funding when rate > 0
            self.equity += pnl
            st.equity_contrib += pnl

        self.peak_equity = max(self.peak_equity, self.equity)
        if self.peak_equity > 0:
            self.max_dd = max(self.max_dd, (self.peak_equity - self.equity) / self.peak_equity)
        self._publish(ts)

    def _publish(self, ts: int) -> None:
        pnl = self.equity - self.starting_capital
        self.reporter.state(
            balance=round(self.equity, 4),
            today_pnl_abs=round(pnl, 4),
            today_pnl_pct=round(pnl / self.starting_capital * 100, 3),
            win_rate=round(sum(1 for s in self.pairs.values() if s.in_market)
                           / len(self.pairs) * 100, 1),
            is_connected=True,
        )

    def summary(self, days: float) -> dict:
        total_return = (self.equity / self.starting_capital - 1) * 100
        annualized = ((self.equity / self.starting_capital) ** (365.0 / days) - 1) * 100 if days > 0 else 0.0
        return {
            "final_equity": self.equity,
            "total_return_pct": total_return,
            "annualized_pct": annualized,
            "max_drawdown_pct": self.max_dd * 100,
            "per_pair": {p: round(s.equity_contrib, 4) for p, s in self.pairs.items()},
        }


def merge_funding(streams: Dict[str, Sequence[Tuple[int, float, float]]]
                  ) -> List[Tuple[int, str, float]]:
    """Interleave per-pair funding streams into one time-ordered event list."""
    events: List[Tuple[int, str, float]] = []
    for pair, rows in streams.items():
        for ts, _hrs, rate in rows:
            events.append((ts, pair, rate))
    events.sort(key=lambda e: e[0])
    return events
