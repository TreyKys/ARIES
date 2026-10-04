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
