"""The one backtest loop for the COMBINED BOOK (trend + cross-sectional
reversal). Distinct from ares/backtest.py, which is the original ARES-1
single-instrument engine for TrendPullbackStrategy and is unrelated.

Extracted from run_aries_futures.run_replay so the live runner and every
research script execute IDENTICAL code. Three strategies in this repo once
reported profits that did not exist, each from its own hand-written P&L; the
same failure mode applies to a hand-copied backtest loop, where a research
script slowly drifts from the thing that will actually trade.

Everything routes through the audited Ledger, so equity is always
cash + sum(position * price).
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

from .combined import Signal, combined_signal, size_positions
from .ledger import Ledger

# Measured round-trip cost for CME micro futures: commission plus one tick on
# a $30,000-44,000 contract. Crypto spot was 15bp, which is what killed the
# high-frequency variants.
COST_BPS = 0.75e-4

# Without a no-trade band, daily vol and equity drift flip whole-contract
# counts between n and n+-1 endlessly: measured $31,480 of fees on a $25k
# account over 26 years, about 5%/yr of capital. Act only on a real signal
# change, not on rounding jitter.
NO_TRADE_BAND = 0.34


def backtest(px: pd.DataFrame, mult: Dict[str, float], *, capital: float,
             target_vol: float = 0.03, w_trend: float = 0.5, top_k: int = 3,
             max_contracts: int = 3, warmup: int = 253,
             trend_lookback: int = 252, vol_window: int = 0,
             mask_zero_returns: bool = False, vol_floor_frac: float = 0.25,
             signal_fn=None, signal_window: Optional[int] = None,
             cost_bps: float = COST_BPS,
             on_trade: Optional[Callable] = None,
             on_mark: Optional[Callable] = None) -> Ledger:
    """Run the combined book over a price panel. Returns the ledger.

    px   : one column per tradeable symbol, already sign-corrected.
    mult : contract multiplier per symbol.

    Rebalances DAILY. The reversal leg's edge lives at a one-day horizon;
    rebalancing monthly measured Sharpe +0.22 against +0.82 for the same
    universe rebalanced daily. The trend leg moves slowly, so daily
    rebalancing costs it little extra turnover.
    """
    led = Ledger(capital)
    # mask_zero_returns defaults OFF, and that is a measured decision, not an
    # oversight. Masking exact zeros is the right fix when an index carries
    # per-market session timestamps (see ares/factors.py, where ffill runs
    # collapsed a volatility estimate into 246x leverage). It is WRONG here:
    # this panel is forward-filled onto a union calendar, so every market's
    # own holidays become exact zeros. Masking them leaves a 60-day window
    # with fewer than 30 usable points, the estimate becomes NaN, the market
    # drops out of sizing, and the book stops trading -- measured as 0.00%
    # volatility and no trades at all across 19 markets. The vol FLOOR in
    # size_positions is the robust fix for the same hazard, and it costs
    # nothing: Sharpe 0.54 -> 0.54 on 8 markets, 0.47 -> 0.48 on 19.
    rets = px.pct_change()
    if mask_zero_returns:
        rets = rets.where(rets != 0)
    vol_w = rets.rolling(60, min_periods=30).std() * np.sqrt(252)
    # A trailing window, not the whole history. combined_signal reads exactly
    # two rows (the last, and the one trend_lookback back), so a fixed window
    # gives IDENTICAL results while turning an O(n^2) loop into O(n). On the
    # 56-year panel the growing slice was the entire cost of the backtest.
    # signal_fn lets a research script swap in any candidate edge while
    # keeping the identical sizing, cost and ledger path, so two edges are
    # never compared across two different backtests.
    need = signal_window or (trend_lookback + 2)
    for i in range(warmup, len(px)):
        win = px.iloc[max(0, i + 1 - need): i + 1]
        ts = int(win.index[-1].value // 1_000_000)
        prices = {c: float(win[c].iloc[-1]) for c in win.columns
                  if np.isfinite(win[c].iloc[-1])}
        if not prices:
            continue
        if signal_fn is None:
            sig = combined_signal(win, w_trend=w_trend, top_k=top_k,
                                  trend_lookback=trend_lookback,
                                  vol_window=vol_window)
        else:
            w = signal_fn(win, top_k)
            sig = Signal(weights={k: float(v) for k, v in w.items() if v},
                         asof=win.index[-1])
        vols = {c: float(vol_w[c].iloc[i]) for c in win.columns
                if np.isfinite(vol_w[c].iloc[i])}
        want = size_positions(sig, prices, capital=led.equity() or capital,
                              target_vol=target_vol, vols=vols,
                              contract_multiplier=mult,
                              max_contracts_per_market=max_contracts,
                              vol_floor_frac=vol_floor_frac)
        for c in prices:
            tgt = want.get(c, 0) * mult.get(c, 1.0)
            cur = led.pos.get(c, 0.0)
            dq = tgt - cur
            band = NO_TRADE_BAND * max(abs(tgt), abs(cur), 1e-9)
            if abs(dq) > 1e-9 and (abs(dq) >= band or tgt == 0.0
                                   or np.sign(tgt) != np.sign(cur)):
                fee = abs(dq) * prices[c] * cost_bps
                led.trade(ts, c, dq, prices[c], cost=fee)
                if on_trade:
                    on_trade(ts, c, dq, prices[c], fee)
        eq = led.mark(ts, prices)
        if on_mark:
            on_mark(i, ts, eq, prices, led)
    return led
