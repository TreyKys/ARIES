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


def backtest_adaptive_grid(candles: Sequence, *, atr_period: int = 48,
                           spacing_atr: float = 0.5, max_inventory: int = 20,
                           maker_fee: float = 0.0002, capital: float = 50.0,
                           trend_fast: int = 50, trend_slow: int = 200,
                           trend_gate: bool = True, flatten_on_trend: bool = False):
    """Adaptive trailing step-grid with volatility-scaled spacing and a
    trend gate.

    - spacing = spacing_atr * ATR  -> the band auto-adjusts to volatility.
    - buy every `spacing` down, sell every `spacing` up (trailing, no fixed
      band, so it follows price instead of holding a far-away bag).
    - trend gate: in a confirmed downtrend (fast EMA < slow EMA) stop
      buying; optionally flatten the bag (bounded loss) and wait. This is
      the protection against averaging into a falling knife.
    """
    from . import indicators
    import numpy as np
    h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
    cl = np.array([c.close for c in candles]); ts = [c.ts for c in candles]
    atr = indicators.atr(h, l, cl, atr_period)
    ef = indicators.ema(cl, trend_fast); es = indicators.ema(cl, trend_slow)
    n = len(cl)
    unit = capital / max_inventory
    inventory: List[float] = []        # buy prices (FIFO)
    realized = 0.0
    round_trips = 0
    peak = capital; max_dd = 0.0
    curve = []
    warm = max(atr_period, trend_slow) + 1
    last = cl[warm]
    for i in range(warm, n):
        p = cl[i]
        sp = spacing_atr * atr[i]
        if not np.isfinite(sp) or sp <= 0:
            continue
        downtrend = trend_gate and ef[i] < es[i]

        if downtrend and flatten_on_trend and inventory:
            for bp in inventory:
                realized += (p / bp - 1) * unit - 2 * maker_fee * unit
            inventory.clear(); last = p

        # sells: price stepped up through rungs
        while inventory and p >= last + sp:
            bp = inventory.pop(0)
            sell = last + sp
            realized += (sell / bp - 1) * unit - 2 * maker_fee * unit
            round_trips += 1
            last = last + sp
        # buys: price stepped down through rungs (blocked in downtrend)
        while (not downtrend) and len(inventory) < max_inventory and p <= last - sp:
            last = last - sp
            inventory.append(last)

        # keep 'last' near price even when idle so we don't jump many rungs at once
        if not inventory and not (downtrend and not flatten_on_trend):
            last = p

        unreal = sum((p / bp - 1) * unit for bp in inventory)
        eq = capital + realized + unreal
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        curve.append((ts[i], eq))

    final = capital + realized + sum((cl[-1] / bp - 1) * unit for bp in inventory)
    return GridResult(round_trips, realized, (final / capital - 1) * 100,
                      max_dd * 100, final, curve)


def _two_leg_grid(cl, ts, *, spacing_frac, max_inventory, cost_rt, hedge_ratio,
                  funding_long_8h, funding_short_8h, capital):
    """Honest two-leg grid: marks BOTH the long inventory and the short hedge.

    P&L identity: for any book, price P&L = sum(position * dPrice). A book held
    delta-neutral therefore earns NOTHING from price movement -- only carry,
    minus costs. The hedge is a mirror-image grid: it shorts as price falls and
    covers as it rises, giving back exactly what the long grid earns. Any model
    that books the long leg's round trips while charging the hedge only fees
    reports phantom profit. This one does not.
    """
    unit = capital / max_inventory
    inv: List[float] = []
    hedge_units = 0.0; hedge_basis = 0.0
    cash = 0.0; fees = 0.0; funding = 0.0; hits = 0
    last = cl[0]; last_f = ts[0]
    peak = capital; max_dd = 0.0; curve = []
    half = cost_rt / 2.0

    def mtm(p):
        long_pnl = sum((p / bp - 1) * unit for bp in inv)
        short_pnl = (hedge_basis / p - 1) * hedge_units * unit if hedge_units > 0 else 0.0
        return capital + cash + funding - fees + long_pnl + short_pnl

    for i in range(1, len(cl)):
        p = cl[i]
        while inv and p >= last * (1 + spacing_frac):          # sell a long rung
            bp = inv.pop(0); sell = last * (1 + spacing_frac)
            cash += (sell / bp - 1) * unit; fees += half * unit
            hits += 1; last = sell
            tgt = hedge_ratio * len(inv)
            if hedge_units > tgt:                              # shrink hedge: realize short P&L
                close = hedge_units - tgt
                cash += (hedge_basis / p - 1) * close * unit
                fees += half * close * unit
                hedge_units = tgt
        while len(inv) < max_inventory and p <= last * (1 - spacing_frac):
            last = last * (1 - spacing_frac); inv.append(last)
            fees += half * unit
            tgt = hedge_ratio * len(inv)
            if tgt > hedge_units:                              # add hedge at current price
                add = tgt - hedge_units
                hedge_basis = ((hedge_basis * hedge_units) + p * add) / (hedge_units + add)
                hedge_units = tgt; fees += half * add * unit
        if not inv:
            last = p
        if ts[i] - last_f >= 8 * 3600 * 1000:
            funding += (funding_short_8h * hedge_units * unit
                        - funding_long_8h * len(inv) * unit)
            last_f = ts[i]
        eq = mtm(p)
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        curve.append((ts[i], eq))
    final = mtm(cl[-1])
    return GridResult(hits, cash - fees + funding, (final / capital - 1) * 100,
                      max_dd * 100, final, curve)


def backtest_hedged_grid(candles: Sequence, *, spacing_pct: float = 0.005,
                         use_atr: bool = False, atr_mult: float = 0.7, atr_period: int = 48,
                         max_inventory: int = 20, maker_fee: float = 0.0002,
                         taker_fee: float = 0.0005, funding_8h: float = 0.0001,
                         min_edge_mult: float = 2.0, capital: float = 50.0,
                         hedge_ratio: float = 1.0):
    """Grid with an optional short hedge, honestly marked on BOTH legs.

    `hedge_ratio` 1.0 = delta-neutral, 0.0 = plain long grid. Be clear-eyed
    about what the hedge does: it removes the directional bag AND the
    oscillation profit together, leaving only funding carry minus fees.
    A neutral book cannot harvest movement -- see `_two_leg_grid`.

    Funding here is credited on the SHORT leg only (long leg = spot, pays
    none), i.e. the spot+perp carry trade. For an all-perp book the long leg
    pays what the short collects, so pass the perp variant below instead.
    """
    import numpy as np
    from . import indicators
    cl = np.array([c.close for c in candles]); ts = [c.ts for c in candles]
    cost_rt = 2 * maker_fee + 2 * taker_fee
    if use_atr:
        h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
        a = indicators.atr(h, l, cl, atr_period)
        med = float(np.nanmedian(a[atr_period + 1:] / cl[atr_period + 1:]))
        sp = max(atr_mult * med, min_edge_mult * cost_rt)
        w = atr_period + 1
        cl, ts = cl[w:], ts[w:]
    else:
        sp = max(spacing_pct, min_edge_mult * cost_rt)
    return _two_leg_grid(cl, ts, spacing_frac=sp, max_inventory=max_inventory,
                         cost_rt=cost_rt, hedge_ratio=hedge_ratio,
                         funding_long_8h=0.0, funding_short_8h=funding_8h,
                         capital=capital)


def backtest_perp_hedged_grid(candles: Sequence, *, spacing_pct: float = 0.005,
                              use_atr: bool = True, atr_mult: float = 0.7, atr_period: int = 48,
                              max_inventory: int = 20, maker_fee: float = 0.0002,
                              taker_fee: float = 0.0005,
                              funding_long_8h: float = 0.0001,
                              funding_short_8h: float = 0.0001,
                              min_edge_mult: float = 2.0, capital: float = 50.0,
                              hedge_ratio: float = 1.0, leverage: float = 3.0):
    """All-perp grid (both legs perps in ONE account, e.g. a prop account).

    Prop-firm compatible in STRUCTURE, but see the arithmetic: with both legs
    on the same symbol the long pays exactly what the short collects, so
    funding cancels -- and a neutral book earns nothing from movement. The
    all-perp neutral grid is therefore a guaranteed loss (fees only). It is
    kept here because that is a result worth being able to reproduce, and
    because `hedge_ratio < 1` turns it into an honest directional grid.
    """
    import numpy as np
    from . import indicators
    cl = np.array([c.close for c in candles]); ts = [c.ts for c in candles]
    cost_rt = 2 * maker_fee + 2 * taker_fee
    if use_atr:
        h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
        a = indicators.atr(h, l, cl, atr_period)
        med = float(np.nanmedian(a[atr_period + 1:] / cl[atr_period + 1:]))
        sp = max(atr_mult * med, min_edge_mult * cost_rt)
        w = atr_period + 1
        cl, ts = cl[w:], ts[w:]
    else:
        sp = max(spacing_pct, min_edge_mult * cost_rt)
    return _two_leg_grid(cl, ts, spacing_frac=sp, max_inventory=max_inventory,
                         cost_rt=cost_rt, hedge_ratio=hedge_ratio,
                         funding_long_8h=funding_long_8h,
                         funding_short_8h=funding_short_8h, capital=capital)
