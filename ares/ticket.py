"""Order tickets for MANUAL entry -- the Phidias-compliant way to run the book.

Phidias's rules (read 2026-10-13): "The use of robots, fully automated
trading algorithms, or any other form of automated trading is not
permitted. Only semi-automated software is permitted, provided the trader
actively monitors and manually adjusts all trades."

So on a Phidias account this system must never send an order. It computes
the target book and prints exactly what to type into Tradovate or Rithmic;
the trader places every order by hand. The book rebalances once a day, about
ten minutes before the 16:00 New York close, so this is a few clicks a day.

Pure functions only here, so the ticket logic is testable without a broker,
a network connection, or a clock.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .combined import check_viable, combined_signal, size_positions
from .costs import cheapest


@dataclass
class Order:
    symbol: str
    side: str            # BUY / SELL
    qty: int
    have: int
    want: int
    est_cost_usd: float


@dataclass
class Ticket:
    asof: str
    equity: float
    orders: List[Order]
    targets: Dict[str, int]
    excluded: List[str]
    est_cost_usd: float
    warnings: List[str]

    def as_dict(self):
        d = asdict(self)
        d["orders"] = [asdict(o) for o in self.orders]
        return d


def append_quotes(px: pd.DataFrame, quotes: Dict[str, float],
                  asof: pd.Timestamp) -> pd.DataFrame:
    """Add today's live prices as the newest row, without duplicating a day
    the history file already contains."""
    asof = pd.Timestamp(asof).normalize()
    row = pd.Series({c: quotes.get(c, np.nan) for c in px.columns}, name=asof)
    base = px[px.index.normalize() < asof]
    return pd.concat([base, row.to_frame().T])


def build_ticket(px_hist: pd.DataFrame, quotes: Dict[str, float], *,
                 equity: float, positions: Dict[str, int],
                 mult: Dict[str, float], asof: pd.Timestamp,
                 target_vol: float, w_trend: float = 0.0, top_k: int = 3,
                 max_contracts: int = 3, max_staleness_days: int = 5
                 ) -> Ticket:
    warnings: List[str] = []
    last = px_hist.index[-1]
    gap = (pd.Timestamp(asof).normalize() - last.normalize()).days
    if gap > max_staleness_days:
        raise ValueError(
            f"history ends {last.date()}, {gap} days before {pd.Timestamp(asof).date()}"
            " -- refresh data/daily before trading on it")
    excluded = [c for c in px_hist.columns
                if not (quotes.get(c) and np.isfinite(quotes[c]) and quotes[c] > 0)]
    live_cols = [c for c in px_hist.columns if c not in excluded]
    check_viable(equity, live_cols)
    if excluded:
        warnings.append(f"no live quote for {', '.join(excluded)}: excluded "
                        "today, and any position in them is left alone")
    px = append_quotes(px_hist[live_cols], quotes, asof)
    sig = combined_signal(px, w_trend=w_trend, top_k=top_k)
    vol = px.pct_change().rolling(60, min_periods=30).std().iloc[-1] * np.sqrt(252)
    prices = {c: float(px[c].iloc[-1]) for c in live_cols}
    want = size_positions(sig, prices, capital=equity, target_vol=target_vol,
                          vols={c: float(vol[c]) for c in live_cols
                                if np.isfinite(vol[c])},
                          contract_multiplier=mult,
                          max_contracts_per_market=max_contracts)
    orders: List[Order] = []
    for c in sorted(live_cols):
        have = int(positions.get(c, 0))
        tgt = int(want.get(c, 0))
        dq = tgt - have
        if dq:
            cost = abs(dq) * cheapest(c).side_usd() if c in _COSTED else 0.0
            orders.append(Order(c, "BUY" if dq > 0 else "SELL", abs(dq),
                                have, tgt, round(cost, 2)))
    return Ticket(asof=str(pd.Timestamp(asof).date()), equity=equity,
                  orders=orders, targets={c: int(want.get(c, 0)) for c in live_cols},
                  excluded=excluded,
                  est_cost_usd=round(sum(o.est_cost_usd for o in orders), 2),
                  warnings=warnings)


_COSTED = {"MES", "MNQ", "MYM", "M2K", "MGC", "SIL", "MCL", "M6E", "M6A",
           "M6B", "MBT", "MET"}


def format_ticket(t: Ticket) -> str:
    lines = [f"ORDER TICKET  {t.asof}  account equity ${t.equity:,.0f}",
             "Place these MANUALLY in Tradovate/Rithmic, ~16:05-16:10 New York.",
             "This software does not and must not send orders on a Phidias account.",
             ""]
    if not t.orders:
        lines.append("  no changes today -- hold current positions")
    for o in t.orders:
        lines.append(f"  {o.side:4s} {o.qty:>3d} {o.symbol:<4s}   "
                     f"(have {o.have:+d}, want {o.want:+d})  ~${o.est_cost_usd:.2f}")
    if t.orders:
        lines.append(f"\n  estimated cost of today's ticket: ${t.est_cost_usd:.2f}")
    for w in t.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
