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


def test_neutral_grid_cannot_harvest_oscillation():
    """THE identity: a delta-neutral book earns nothing from price movement.

    On a pure sine wave with ZERO fees -- the most grid-friendly market that
    can exist -- a fully hedged grid must NOT turn a profit. An earlier model
    booked the long leg's round trips while charging the hedge only fees and
    reported ~+11%/yr of phantom return; this pins that bug shut.
    """
    import math
    from ares.grid import backtest_hedged_grid
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(4000)]
    neutral = backtest_hedged_grid(_mk(prices), spacing_pct=0.01, atr_period=20,
                                   maker_fee=0.0, taker_fee=0.0, funding_8h=0.0,
                                   min_edge_mult=0.0, hedge_ratio=1.0, capital=100.0)
    assert neutral.round_trips > 0                 # it did trade
    assert neutral.net_return_pct <= 0.0           # and earned nothing from it


def test_unhedged_grid_harvests_what_the_hedge_gives_away():
    # Same path, no hedge: the oscillation profit is real but DIRECTIONAL.
    import math
    from ares.grid import backtest_hedged_grid
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(4000)]
    kw = dict(spacing_pct=0.01, atr_period=20, maker_fee=0.0, taker_fee=0.0,
              funding_8h=0.0, min_edge_mult=0.0, capital=100.0)
    plain = backtest_hedged_grid(_mk(prices), hedge_ratio=0.0, **kw)
    neutral = backtest_hedged_grid(_mk(prices), hedge_ratio=1.0, **kw)
    assert plain.net_return_pct > neutral.net_return_pct


def test_neutral_grid_income_is_carry_only():
    # Fully hedged, fee-free: the ONLY thing that can move equity is funding
    # credited on the short leg (the spot+perp carry trade).
    import math
    from ares.grid import backtest_hedged_grid
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(4000)]
    kw = dict(spacing_pct=0.01, atr_period=20, maker_fee=0.0, taker_fee=0.0,
              min_edge_mult=0.0, hedge_ratio=1.0, capital=100.0)
    nocarry = backtest_hedged_grid(_mk(prices), funding_8h=0.0, **kw)
    carry = backtest_hedged_grid(_mk(prices), funding_8h=0.0002, **kw)
    assert carry.net_return_pct > nocarry.net_return_pct


def test_all_perp_neutral_grid_is_a_guaranteed_loss():
    # Both legs same symbol: long pays what short collects -> funding cancels,
    # neutral book earns nothing from movement, fees remain. Must lose.
    import math
    from ares.grid import backtest_perp_hedged_grid
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(4000)]
    r = backtest_perp_hedged_grid(_mk(prices), use_atr=False, spacing_pct=0.01,
                                  atr_period=20, maker_fee=0.0002, taker_fee=0.0005,
                                  funding_long_8h=0.0001, funding_short_8h=0.0001,
                                  hedge_ratio=1.0, capital=100.0)
    assert r.net_return_pct < 0.0
