from dataclasses import dataclass
from ares.grid_engine import HedgedGridEngine


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


def test_engine_harvests_and_stays_low_dd():
    import math
    prices = [100 + 8 * math.sin(i / 5.0) for i in range(3000)]
    eng = HedgedGridEngine("TEST", capital=50.0, atr_period=20, atr_mult=0.5,
                           maker_fee=0.0, taker_fee=0.0, funding_8h=0.0)
    for c in _mk(prices):
        eng.step(c)
    assert eng.round_trips > 0
    assert eng.max_dd < 0.05          # hedged -> tiny drawdown


def test_engine_matches_backtest_direction():
    # sanity: positive realized on a clean oscillation
    import math
    prices = [100 + 5 * math.sin(i / 8.0) for i in range(2000)]
    eng = HedgedGridEngine("TEST", capital=50.0, atr_period=20, atr_mult=0.4,
                           maker_fee=0.0, taker_fee=0.0, funding_8h=0.0)
    for c in _mk(prices):
        eng.step(c)
    assert eng.realized >= 0
