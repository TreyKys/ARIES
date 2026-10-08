"""The combined book: trend + cross-sectional reversal, through the ledger.

This is the one directional result in this repo that survived every check
applied to it (see docs/STRATEGY_RESEARCH.md):

    trend (tsmom) alone      Sharpe +0.70 +/-0.21  t=4.71   57yr
    reversal alone           Sharpe +0.50 +/-0.14  t=3.50   57yr
    50/50 combined           Sharpe +0.84 +/-0.16  t=5.37   57yr

The two components correlate +0.007 -- effectively independent -- which is why
combining them raises Sharpe AND nearly halves max drawdown (34% -> 19%). The
smoothness is the point: it is what allows a workable position size inside a
drawdown limit.

What the reversal leg is, in plain terms: it is the GRID, with the flaw removed.
A grid buys dips and sells rips on one instrument, and dies because in a
downtrend it accumulates a losing bag -- while hedging it cancels the profit
exactly (ares/ledger.py pins that identity). This buys the markets that dipped
RELATIVE TO THE BASKET and shorts those that popped, so it is market-neutral by
construction with no hedge and no directional bag to accumulate.

Capital reality, measured: the book needs at least 6 simultaneous markets and
preferably 8. At 4 markets it returns Sharpe -0.11, i.e. it loses. Holding 8
diversified micro futures overnight needs roughly $7,750-12,700 of margin, so
MIN_VIABLE_CAPITAL below is enforced rather than advisory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

MIN_MARKETS = 6
TARGET_MARKETS = 8
MIN_VIABLE_CAPITAL = 15_000.0

# Approximate CME overnight maintenance margin per micro contract.
MARGIN = {"MES": 2400, "MNQ": 3100, "MYM": 1100, "M2K": 900, "MGC": 1200,
          "SIL": 1400, "MCL": 1400, "M6E": 300, "M6A": 250, "M6B": 350,
          "MJY": 350, "ZF": 1200, "ZN": 1500}


class CapitalTooSmall(RuntimeError):
    pass


def check_viable(capital: float, markets: Sequence[str],
                 utilisation: float = 0.6) -> None:
    """Refuse to run a configuration that was measured to lose money.

    Four markets measured Sharpe -0.11. Silently running an under-capitalised
    book is how a validated strategy turns into a losing one, so this raises
    rather than warns.
    """
    if len(markets) < MIN_MARKETS:
        raise CapitalTooSmall(
            f"{len(markets)} markets: the book needs >= {MIN_MARKETS} "
            f"(4 markets measured Sharpe -0.11, i.e. a loss)")
    need = sum(MARGIN.get(m, 1500) for m in markets)
    budget = capital * utilisation
    if need > budget:
        raise CapitalTooSmall(
            f"${capital:,.0f} at {utilisation:.0%} utilisation gives "
            f"${budget:,.0f} of margin budget, but holding {len(markets)} "
            f"markets overnight needs ~${need:,.0f}. Minimum viable capital "
            f"for this book is about ${MIN_VIABLE_CAPITAL:,.0f}.")


@dataclass
class Signal:
    """Target weight per market, in [-1, 1], from the combined book."""
    weights: Dict[str, float] = field(default_factory=dict)
    trend: Dict[str, float] = field(default_factory=dict)
    reversal: Dict[str, float] = field(default_factory=dict)
    asof: Optional[pd.Timestamp] = None


def trend_weights(px: pd.DataFrame, lookback: int = 252) -> pd.Series:
    """sign of the trailing 12-month return (Moskowitz/Ooi/Pedersen)."""
    tr = px.iloc[-1] / px.iloc[-1 - lookback] - 1.0
    return np.sign(tr).fillna(0.0)


def reversal_weights(px: pd.DataFrame, lookback: int = 1,
                     top_k: int = 3) -> pd.Series:
    """Long the biggest laggards vs the basket, short the biggest leaders.

    The common market factor is removed by demeaning across the universe, so
    what is ranked is the idiosyncratic move -- the part that reverts.
    """
    r = px.iloc[-1] / px.iloc[-1 - lookback] - 1.0
    r = r.dropna()
    if len(r) < MIN_MARKETS:
        return pd.Series(0.0, index=px.columns)
    r = r - r.mean()
    order = r.sort_values().index
    k = min(top_k, len(order) // 2)
    w = pd.Series(0.0, index=px.columns)
    w.loc[order[:k]] = 1.0            # fell most vs basket -> buy
    w.loc[order[-k:]] = -1.0          # rose most vs basket -> short
    return w


def combined_signal(px: pd.DataFrame, *, trend_lookback: int = 252,
                    reversal_lookback: int = 1, top_k: int = 3,
                    w_trend: float = 0.5) -> Signal:
    """Blend the two legs. 50/50 by default -- deliberately NOT optimised,
    since fitted weights are how the earlier phantoms were produced."""
    if len(px) <= trend_lookback + 1:
        return Signal(asof=px.index[-1] if len(px) else None)
    t = trend_weights(px, trend_lookback)
    r = reversal_weights(px, reversal_lookback, top_k)
    w = (w_trend * t + (1.0 - w_trend) * r).clip(-1.0, 1.0)
    return Signal(weights=w.to_dict(), trend=t.to_dict(),
                  reversal=r.to_dict(), asof=px.index[-1])


def size_positions(sig: Signal, prices: Dict[str, float], *,
                   capital: float, target_vol: float,
                   vols: Dict[str, float],
                   contract_multiplier: Dict[str, float],
                   max_contracts_per_market: int = 3) -> Dict[str, int]:
    """Convert weights into whole contract counts at a risk budget.

    Each market is scaled to an equal volatility contribution, then rounded to
    whole contracts -- futures cannot be traded fractionally, and ignoring that
    is a common way backtests overstate achievable precision.
    """
    live = [m for m, w in sig.weights.items()
            if w and m in prices and m in vols and vols[m] > 0]
    if not live:
        return {}
    per_market_vol = target_vol / np.sqrt(len(live))
    out: Dict[str, int] = {}
    for m in live:
        notional = (per_market_vol * capital) / vols[m]
        mult = contract_multiplier.get(m, 1.0)
        contracts = notional / max(prices[m] * mult, 1e-9)
        n = int(np.clip(round(contracts * sig.weights[m]),
                        -max_contracts_per_market, max_contracts_per_market))
        if n:
            out[m] = n
    return out
