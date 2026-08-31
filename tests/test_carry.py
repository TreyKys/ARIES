import numpy as np
import pytest

from ares.carry import CarryConfig, run_carry
from ares.strategy import Bars, DonchianBreakoutStrategy
from ares.types import Side


def _funding(n, rate, start=1_700_000_000_000, step=8 * 3_600_000):
    return [(start + i * step, 8.0, rate) for i in range(n)]


def test_carry_collects_positive_funding():
    res = run_carry(_funding(100, 0.0001), starting_capital=50.0,
                    cfg=CarryConfig(taker_fee=0.0, always_on=True))
    # 100 intervals * 0.0001 * $50 notional = $0.50, no fees
    assert res.final_equity == pytest.approx(50.0 + 0.50, abs=1e-9)
    assert res.metrics["max_drawdown_pct"] < 0.001


def test_carry_pays_negative_funding():
    res = run_carry(_funding(50, -0.0002), starting_capital=50.0,
                    cfg=CarryConfig(taker_fee=0.0, always_on=True))
    assert res.final_equity < 50.0            # negative funding bleeds an always-on carry


def test_carry_is_deterministic():
    f = _funding(200, 0.00008)
    a = run_carry(f, 50.0, CarryConfig(always_on=True))
    b = run_carry(f, 50.0, CarryConfig(always_on=True))
    assert a.final_equity == b.final_equity


def test_breakout_triggers_long_on_new_high():
    # steady uptrend -> latest close breaks above the prior-N high
    close = np.linspace(100, 130, 60)
    bars = Bars(ts=np.arange(60, dtype=np.int64) * 3_600_000,
                open=close, high=close * 1.001, low=close * 0.999,
                close=close, volume=np.full(60, 1.0))
    d = DonchianBreakoutStrategy(channel=20, atr_mult=2.0, reward_multiple=2.0).evaluate(bars)
    assert d is not None and d.side is Side.LONG
    assert d.stop_price < close[-1] < d.take_profit_price
