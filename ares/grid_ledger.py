"""Unhedged mean-reversion grid, routed through the audited ledger.

What this is and is not. The HEDGED grid is dead by arithmetic: a short hedge
sized to the long inventory is a mirror-image grid, so it hands back exactly
what the grid earns, and a delta-neutral book earns nothing from price movement
(ares/ledger.py pins the identity; on a pure sine wave with zero fees the hedged
version returns -68%). That cannot be tuned away.

The UNHEDGED grid is a different animal and is real: buy fixed steps down, sell
fixed steps up. It earns when price oscillates and loses when price trends away,
leaving an inventory bag. That is genuine directional risk, not a bookkeeping
artifact -- on the same sine wave it returns +107%.

Because every fill and every mark goes through Ledger, equity here is always
cash + position * price. There is no path that credits a "round-trip profit",
so the bag is always carried at its real mark and the drawdown is honest.

Risk framing note: this strategy's drawdowns are large (tens of percent). That
disqualifies it for a prop account with a 6% limit, but a 40% drawdown on a $50
stake is $20, so the relevant question for a small own-capital account is growth
per unit of ACCEPTABLE loss, not institutional Sharpe.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .ledger import Ledger

SYMBOL = "ASSET"


def run_grid(ts: Sequence[int], px: Sequence[float], *,
             capital: float = 50.0,
             spacing_pct: float = 0.01,
             max_inventory: int = 20,
             cost_bps: float = 10.0,
             atr_window: int = 0,
             atr_mult: float = 0.7,
             min_spacing_mult: float = 2.0,
             trend_exit_ema: int = 0) -> Ledger:
    """Buy a rung every `spacing` down, sell a rung every `spacing` up.

    spacing is either a fixed fraction (`spacing_pct`) or volatility-scaled
    (`atr_window > 0` uses a rolling mean absolute return * atr_mult). It is
    floored at `min_spacing_mult * cost` so a rung always clears its own fees --
    the optimum spacing for a diffusion is 2x cost.

    trend_exit_ema: if > 0, flatten and stop buying while price is below that
      EMA. This is the one real defence against the trend bag, and unlike the
      hedge it does not cancel the oscillation profit -- it just stands aside.
    """
    led = Ledger(capital)
    unit_cash = capital / max_inventory
    cost_rate = cost_bps / 1e4
    inv: List[float] = []          # entry prices, FIFO
    last = float(px[0])
    ema: Optional[float] = None
    k = 2.0 / (trend_exit_ema + 1.0) if trend_exit_ema > 0 else 0.0
    absret: List[float] = []
    prev = float(px[0])

    for i in range(len(px)):
        p = float(px[i])
        t = int(ts[i])
        if p <= 0:
            continue
        if ema is None:
            ema = p
        else:
            ema += k * (p - ema) if trend_exit_ema > 0 else 0.0
        if atr_window > 0:
            if prev > 0:
                absret.append(abs(p / prev - 1.0))
                if len(absret) > atr_window:
                    absret.pop(0)
            sp = atr_mult * (sum(absret) / len(absret)) if absret else spacing_pct
        else:
            sp = spacing_pct
        sp = max(sp, min_spacing_mult * 2 * cost_rate)
        prev = p

        downtrend = trend_exit_ema > 0 and ema is not None and p < ema

        if downtrend and inv:
            # stand aside: close the bag at its real mark and stop buying
            qty = led.pos.get(SYMBOL, 0.0)
            if qty > 0:
                led.trade(t, SYMBOL, -qty, p, cost=qty * p * cost_rate)
            inv.clear()
            last = p

        # sell rungs as price steps up
        while inv and p >= last * (1 + sp):
            inv.pop(0)
            q = unit_cash / last          # units bought at that rung
            held = led.pos.get(SYMBOL, 0.0)
            q = min(q, held)
            if q <= 0:
                break
            sell = last * (1 + sp)
            led.trade(t, SYMBOL, -q, sell, cost=q * sell * cost_rate)
            last = sell
        # buy rungs as price steps down
        while (not downtrend) and len(inv) < max_inventory and p <= last * (1 - sp):
            last = last * (1 - sp)
            q = unit_cash / last
            if led.cash < q * last * (1 + cost_rate):
                break                     # no cash: never implicit leverage
            led.trade(t, SYMBOL, q, last, cost=q * last * cost_rate)
            inv.append(last)
        # While flat, the ladder reference may only ratchet UP toward price.
        # Resetting it to price every bar (the obvious-looking way to "keep the
        # ladder near the market") silently disables the strategy: a buy then
        # requires a full spacing move within ONE bar, so a slow decline never
        # triggers anything. The downtrend sanity test caught exactly that --
        # price fell 86% and the grid took zero fills.
        if not inv and p > last:
            last = p

        led.mark(t, {SYMBOL: p})
    return led
