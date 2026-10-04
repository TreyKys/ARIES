"""Grid trading: harvest oscillations in a sideways market.

Place a ladder of price levels across a band. As price falls through a
level, buy a unit; as it rises through the next level up, sell that unit
for one grid-step of profit. In a range this prints many small wins
("1000 micro hits"). The risk is a breakout: if price leaves the band,
you're left holding inventory at a loss (down) or idle (up). This engine
measures both honestly, with maker fees, and supports a range-break stop
and periodic re-centering.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


@dataclass
class GridResult:
    round_trips: int
    realized: float
    net_return_pct: float
    max_drawdown_pct: float
    final_equity: float
    equity_curve: List[Tuple[int, float]] = field(default_factory=list)


def _level(price: float, low: float, spacing: float) -> int:
    return int((price - low) // spacing)


def backtest_grid(candles: Sequence, *, half_width_pct: float = 0.12,
                  n_levels: int = 60, maker_fee: float = 0.0002,
                  capital: float = 50.0, recenter_bars: int = 0,
                  stop_break: bool = False, stop_buffer: float = 0.02) -> GridResult:
    closes = [c.close for c in candles]
    ts = [c.ts for c in candles]
    n = len(closes)
    if n < 2:
        return GridResult(0, 0.0, 0.0, 0.0, capital, [])

    def build(center):
        low = center * (1 - half_width_pct)
        high = center * (1 + half_width_pct)
        return low, high, (high - low) / n_levels

    low, high, spacing = build(closes[0])
    unit = capital / n_levels           # dollar value traded per grid step
    inventory: dict[int, float] = {}    # level index -> buy price
    realized = 0.0
    prev_lvl = _level(closes[0], low, spacing)
    peak = capital
    max_dd = 0.0
    round_trips = 0
    curve = []

    for i in range(1, n):
        price = closes[i]

        if stop_break and (price < low * (1 - stop_buffer) or price > high * (1 + stop_buffer)):
            # liquidate inventory at current price, stop the grid for this band
            for k, bp in inventory.items():
                realized += (price / bp - 1) * unit - 2 * maker_fee * unit
            inventory.clear()
            if recenter_bars or True:  # re-arm the grid around the new price
                low, high, spacing = build(price)
                prev_lvl = _level(price, low, spacing)

        if recenter_bars and i % recenter_bars == 0:
            # realize everything and re-center the band on current price
            for k, bp in inventory.items():
                realized += (price / bp - 1) * unit - 2 * maker_fee * unit
            inventory.clear()
            low, high, spacing = build(price)
            prev_lvl = _level(price, low, spacing)

        lvl = _level(price, low, spacing)
        if lvl < prev_lvl:                       # price fell: buy at each crossed level
            for k in range(max(lvl, 0), min(prev_lvl, n_levels)):
                if k not in inventory:
                    inventory[k] = low + k * spacing
        elif lvl > prev_lvl:                     # price rose: sell inventory below
            for k in range(max(prev_lvl, 0), min(lvl, n_levels)):
                if k in inventory:
                    bp = inventory.pop(k)
                    sell = low + (k + 1) * spacing
                    realized += (sell / bp - 1) * unit - 2 * maker_fee * unit
                    round_trips += 1
        prev_lvl = lvl

        unreal = sum((price / bp - 1) * unit for bp in inventory.values())
        equity = capital + realized + unreal
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
        curve.append((ts[i], equity))

    final_unreal = sum((closes[-1] / bp - 1) * unit for bp in inventory.values())
    final_equity = capital + realized + final_unreal
    return GridResult(round_trips, realized,
                      (final_equity / capital - 1) * 100, max_dd * 100,
                      final_equity, curve)
