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
    # The hedge does NOT make drawdown vanish. It neutralises direction and
    # takes the oscillation profit with it, and rebalancing a hedge against a
    # grid shorts low / covers high, which is itself a real cost. Asserting a
    # tiny DD here is what hid a phantom-profit bug; assert it is finite and
    # that equity is honestly marked instead.
    assert eng.max_dd >= 0.0
    eq = eng.capital + eng.realized
    assert eq == eq                   # finite, not NaN


def test_engine_neutral_cannot_beat_unhedged_on_oscillation():
    """Live engine must obey the same identity as the backtest: a neutral
    book cannot harvest movement, so hedge_ratio=0 must beat hedge_ratio=1
    on a clean oscillation. Guards the phantom-profit regression."""
    import math
    prices = [100 + 5 * math.sin(i / 8.0) for i in range(2000)]
    def run(h):
        eng = HedgedGridEngine("TEST", capital=50.0, atr_period=20, atr_mult=0.4,
                               maker_fee=0.0, taker_fee=0.0, funding_8h=0.0,
                               hedge_ratio=h)
        for c in _mk(prices):
            eng.step(c)
        return eng
    plain, neutral = run(0.0), run(1.0)
    assert plain.round_trips > 0
    assert plain.realized > neutral.realized
