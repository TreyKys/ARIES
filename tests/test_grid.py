from dataclasses import dataclass
from ares.grid import backtest_grid


@dataclass
class C:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def _mk(prices):
    return [C(i * 900_000, p, p, p, p, 1.0) for i, p in enumerate(prices)]


def test_grid_profits_on_oscillation():
    # a clean saw-tooth inside the band should produce round trips and profit
    prices = ([100, 98, 100, 98, 100, 98, 100] * 5)
    r = backtest_grid(_mk(prices), half_width_pct=0.1, n_levels=20,
                      maker_fee=0.0, capital=50.0)
    assert r.round_trips > 0
    assert r.net_return_pct >= 0


def test_grid_holds_bag_on_downtrend():
    # straight downtrend -> inventory underwater, negative unrealized
    prices = list(range(100, 60, -1))
    r = backtest_grid(_mk([float(p) for p in prices]), half_width_pct=0.5,
                      n_levels=40, maker_fee=0.0, capital=50.0)
    assert r.net_return_pct < 0


def test_hedged_grid_low_drawdown_vs_naive():
    # a volatile but mean-reverting path: hedged grid should keep DD small
    import math
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(2000)]
    from ares.grid import backtest_hedged_grid
    r = backtest_hedged_grid(_mk(prices), spacing_pct=0.01, atr_period=20,
                             maker_fee=0.0, taker_fee=0.0, funding_8h=0.0, capital=50.0)
    assert r.round_trips > 0
    assert r.max_drawdown_pct < 5.0           # hedged -> no directional bag


def test_dynamic_hedge_adds_directional_in_uptrend():
    # steady uptrend: smart hedge (ride) should beat full hedge, both finite
    import numpy as np
    prices = list(100 * np.cumprod(1 + np.full(2000, 0.0005)))  # persistent uptrend
    from ares.grid import backtest_hedged_grid
    full = backtest_hedged_grid(_mk(prices), spacing_pct=0.01, atr_period=20,
                                maker_fee=0.0, taker_fee=0.0, funding_8h=0.0,
                                dynamic_hedge=False, capital=100)
    smart = backtest_hedged_grid(_mk(prices), spacing_pct=0.01, atr_period=20,
                                 maker_fee=0.0, taker_fee=0.0, funding_8h=0.0,
                                 dynamic_hedge=True, trend_fast=20, trend_slow=50,
                                 adx_min=0.0, unhedged_ratio=0.0, capital=100)
    assert smart.net_return_pct >= full.net_return_pct


def test_perp_hedged_grid_matches_spot_when_funding_cancels():
    # All-perp (long+short perp, hedge mode) with equal funding on both legs
    # must reproduce the spot+perp grid run WITHOUT funding carry: same hits,
    # same realized grid profit, net funding ~ 0, low drawdown, gross lev > 0.
    import math
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(2000)]
    from ares.grid import backtest_hedged_grid, backtest_perp_hedged_grid
    spot = backtest_hedged_grid(_mk(prices), spacing_pct=0.01, atr_period=20,
                                maker_fee=0.0001, taker_fee=0.0003,
                                funding_8h=0.0, capital=50.0)
    perp = backtest_perp_hedged_grid(_mk(prices), use_atr=False, spacing_pct=0.01,
                                     atr_period=20, maker_fee=0.0001, taker_fee=0.0003,
                                     funding_long_8h=0.0002, funding_short_8h=0.0002,
                                     capital=50.0)
    assert perp.round_trips == spot.round_trips          # identical price mechanics
    assert abs(perp.realized - spot.realized) < 1e-9     # funding cancels -> same P&L
    assert abs(perp.net_funding) < 1e-9                  # long pays what short collects
    assert perp.max_drawdown_pct < 5.0                   # still delta-neutral
    assert perp.peak_gross_leverage > 0.0                # two legs tie up margin


def test_perp_hedged_grid_funding_drag_reduces_return():
    # If the long leg pays MORE funding than the short collects (asymmetry
    # around a rate flip), it is a drag -- never a windfall.
    import math
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(2000)]
    from ares.grid import backtest_perp_hedged_grid
    neutral = backtest_perp_hedged_grid(_mk(prices), use_atr=False, spacing_pct=0.01,
                                        atr_period=20, maker_fee=0.0, taker_fee=0.0,
                                        funding_long_8h=0.0001, funding_short_8h=0.0001,
                                        capital=50.0)
    drag = backtest_perp_hedged_grid(_mk(prices), use_atr=False, spacing_pct=0.01,
                                     atr_period=20, maker_fee=0.0, taker_fee=0.0,
                                     funding_long_8h=0.0003, funding_short_8h=0.0001,
                                     capital=50.0)
    assert drag.net_return_pct < neutral.net_return_pct
    assert drag.net_funding < 0.0
