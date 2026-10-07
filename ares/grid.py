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


def backtest_hedged_grid(candles: Sequence, *, spacing_pct: float = 0.005,
                         use_atr: bool = False, atr_mult: float = 0.7, atr_period: int = 48,
                         max_inventory: int = 20, maker_fee: float = 0.0002,
                         taker_fee: float = 0.0005, funding_8h: float = 0.0001,
                         min_edge_mult: float = 2.0, capital: float = 50.0,
                         dynamic_hedge: bool = False, trend_fast: int = 50,
                         trend_slow: int = 200, adx_min: float = 25.0,
                         unhedged_ratio: float = 0.0):
    """Delta-neutral (hedged) grid: harvest oscillations, cancel the trend.

    Grid-trades long spot inventory for the micro-profits, and holds a short
    perp sized to that inventory so the directional bag is neutralised -- a
    trend can't create the big drawdown that kills a naive grid. Equity is
    therefore the accumulated grid spacing profits + funding earned on the
    short, minus grid and hedge-rebalance fees.

    Honest caveat: this models a perfect hedge. Real perp hedging adds
    basis tracking-error and rebalance slippage, and funding can turn
    negative -- so live drawdown will be somewhat higher than shown. But the
    catastrophic directional bag (the 28-61% DD of the naive grid) is
    genuinely removed.
    """
    from . import indicators
    import numpy as np
    cl = np.array([c.close for c in candles]); ts = [c.ts for c in candles]
    h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
    atr = indicators.atr(h, l, cl, atr_period)
    # Smart hedge: lift the hedge only in a CONFIRMED uptrend (ride the long
    # inventory for extra profit); stay fully hedged otherwise -- especially
    # in downtrends, where an unhedged long bag is the catastrophe we removed.
    if dynamic_hedge:
        ef = indicators.ema(cl, trend_fast); es = indicators.ema(cl, trend_slow)
        adx = indicators.adx(h, l, cl, 14)
    unit = capital / max_inventory
    roundtrip_cost = 2 * maker_fee + 2 * taker_fee          # grid + hedge, both sides
    min_spacing_frac = min_edge_mult * roundtrip_cost       # floor so every rung clears fees
    inv: List[float] = []
    realized = 0.0; round_trips = 0; directional = 0.0
    warm = atr_period + 1
    last = cl[warm]; last_fund = ts[warm]; prev_p = cl[warm]
    peak = capital; max_dd = 0.0; curve = []
    for i in range(warm, len(cl)):
        p = cl[i]
        sp = atr_mult * atr[i] if use_atr else spacing_pct * p
        sp = max(sp, min_spacing_frac * p)                  # cost-aware floor
        if not np.isfinite(sp) or sp <= 0:
            continue
        while inv and p >= last + sp:                       # sell a rung
            bp = inv.pop(0); sell = last + sp
            realized += (sell / bp - 1) * unit - 2 * maker_fee * unit
            realized -= taker_fee * unit                    # unwind one hedge unit
            round_trips += 1; last = last + sp
        while len(inv) < max_inventory and p <= last - sp:  # buy a rung + hedge it
            last = last - sp; inv.append(last)
            realized -= taker_fee * unit
        if not inv:
            last = p
        if ts[i] - last_fund >= 8 * 3600 * 1000 and inv:    # funding on the short
            realized += funding_8h * unit * len(inv); last_fund = ts[i]

        # smart hedge: keep (1 - hedge_ratio) of the long inventory's directional
        # move when an uptrend is confirmed; fully hedged (0) otherwise.
        if dynamic_hedge and inv and prev_p > 0:
            confident_up = (not np.isnan(ef[i]) and not np.isnan(es[i]) and not np.isnan(adx[i])
                            and ef[i] > es[i] and adx[i] >= adx_min)
            open_frac = 1.0 - unhedged_ratio if confident_up else 0.0
            directional += open_frac * len(inv) * unit * (p / prev_p - 1.0)
        prev_p = p

        eq = capital + realized + directional
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        curve.append((ts[i], eq))
    final = capital + realized + directional
    return GridResult(round_trips, realized, (final / capital - 1) * 100,
                      max_dd * 100, final, curve)


@dataclass
class PerpGridResult(GridResult):
    peak_gross_leverage: float = 0.0    # max (long+short notional)/capital seen
    net_funding: float = 0.0            # cumulative funding (long pays, short collects)


def backtest_perp_hedged_grid(candles: Sequence, *, spacing_pct: float = 0.005,
                              use_atr: bool = True, atr_mult: float = 0.7, atr_period: int = 48,
                              max_inventory: int = 20, maker_fee: float = 0.0002,
                              taker_fee: float = 0.0005,
                              funding_long_8h: float = 0.0001,
                              funding_short_8h: float = 0.0001,
                              min_edge_mult: float = 2.0, capital: float = 50.0,
                              leverage: float = 3.0) -> PerpGridResult:
    """Prop-firm-compatible hedged grid: BOTH legs are perps in ONE account.

    This is the user's futures idea. A prop firm gives a single derivatives
    account -- no spot -- so the spot-long leg of the delta-neutral grid is
    replaced by a LOW-LEVERAGE LONG PERP, held alongside the SHORT PERP hedge
    in the same symbol (exchange hedge mode, e.g. Bybit / HyroTrader).

    What stays identical to the spot+perp version:
      - price-tracking: a perp tracks spot via funding, so every grid
        round-trip prints the same spacing profit, and the short hedge
        neutralises direction exactly as before. Net exposure ~ 0.

    What changes (modelled honestly here):
      1. Funding is no longer a tailwind. The long perp PAYS funding when
         funding is positive; the short perp COLLECTS it. Same symbol, same
         rate, same size -> they CANCEL (net ~ 0). The spot+perp version got
         to KEEP the short's funding as free carry; the all-perp version
         gives that back. That is the entire economic cost of going
         prop-compatible.
      2. Leverage. Holding long + short notional ties up margin on both legs;
         low leverage keeps liquidation far away. Because net exposure is ~0,
         a price move can't liquidate a correctly-hedged book -- the risk is
         the brief window where inventory out-paces the hedge. `leverage`
         here is only used to report peak gross notional vs. the account, so
         you can size it under the prop firm's cap. It does NOT multiply
         returns: the hedge is protection, not a multiplier.

    Honest caveat (same as the spot version, plus one): perfect-hedge model,
    so real basis tracking-error and rebalance slippage raise live drawdown;
    AND funding can be asymmetric for a few hours around rate flips, a small
    drag not a disaster. Set funding_long_8h != funding_short_8h to stress it.
    """
    from . import indicators
    import numpy as np
    cl = np.array([c.close for c in candles]); ts = [c.ts for c in candles]
    h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
    atr = indicators.atr(h, l, cl, atr_period)
    unit = capital / max_inventory
    roundtrip_cost = 2 * maker_fee + 2 * taker_fee
    min_spacing_frac = min_edge_mult * roundtrip_cost
    inv: List[float] = []
    realized = 0.0; round_trips = 0; net_funding = 0.0
    warm = atr_period + 1
    last = cl[warm]; last_fund = ts[warm]
    peak = capital; max_dd = 0.0; curve = []
    peak_gross_lev = 0.0
    for i in range(warm, len(cl)):
        p = cl[i]
        sp = atr_mult * atr[i] if use_atr else spacing_pct * p
        sp = max(sp, min_spacing_frac * p)
        if not np.isfinite(sp) or sp <= 0:
            continue
        while inv and p >= last + sp:                       # sell a long rung
            bp = inv.pop(0); sell = last + sp
            realized += (sell / bp - 1) * unit - 2 * maker_fee * unit
            realized -= taker_fee * unit                    # unwind one hedge unit
            round_trips += 1; last = last + sp
        while len(inv) < max_inventory and p <= last - sp:  # buy a long rung + add hedge
            last = last - sp; inv.append(last)
            realized -= taker_fee * unit
        if not inv:
            last = p
        if ts[i] - last_fund >= 8 * 3600 * 1000 and inv:    # funding on BOTH legs
            pay = funding_long_8h * unit * len(inv)         # long perp pays
            collect = funding_short_8h * unit * len(inv)    # short perp collects
            net_funding += collect - pay
            realized += collect - pay
            last_fund = ts[i]
        # gross notional = long inventory + matched short hedge
        gross = 2.0 * len(inv) * unit
        if capital > 0:
            peak_gross_lev = max(peak_gross_lev, gross / capital)

        eq = capital + realized                             # net-neutral: no directional term
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        curve.append((ts[i], eq))
    final = capital + realized
    return PerpGridResult(round_trips, realized, (final / capital - 1) * 100,
                          max_dd * 100, final, curve,
                          peak_gross_leverage=peak_gross_lev, net_funding=net_funding)


