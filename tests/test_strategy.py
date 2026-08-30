import numpy as np
import pytest

from ares import indicators
from ares.strategy import Bars, TrendPullbackStrategy
from ares.types import Side


def _bars_from_close(close: np.ndarray) -> Bars:
    close = np.asarray(close, dtype=float)
    high = close * 1.001
    low = close * 0.999
    return Bars(
        ts=np.arange(close.size, dtype=np.int64) * 300_000,
        open=close, high=high, low=low, close=close,
        volume=np.full(close.size, 1000.0),
    )


def test_returns_none_before_warmup():
    strat = TrendPullbackStrategy()
    bars = _bars_from_close(np.linspace(100, 110, 5))
    assert strat.evaluate(bars) is None


def test_decision_matches_independently_computed_rule():
    """evaluate() must agree with its own documented rule, recomputed here."""
    strat = TrendPullbackStrategy(ema_fast=5, ema_slow=20, rsi_period=14,
                                  rsi_long_max=55.0, atr_period=14,
                                  atr_mult=1.5, reward_multiple=2.0)
    # uptrend then a pullback
    close = np.concatenate([np.linspace(100, 150, 80), np.linspace(150, 140, 12)])
    bars = _bars_from_close(close)

    f = indicators.ema(bars.close, 5)[-1]
    s = indicators.ema(bars.close, 20)[-1]
    r = indicators.rsi(bars.close, 14)[-1]
    a = indicators.atr(bars.high, bars.low, bars.close, 14)[-1]
    c = bars.close[-1]

    decision = strat.evaluate(bars)

    if f > s and r < 55.0 and a > 0:
        assert decision is not None and decision.side is Side.LONG
        assert decision.stop_price < c < decision.take_profit_price
        # reward/risk equals reward_multiple
        risk = c - decision.stop_price
        reward = decision.take_profit_price - c
        assert reward == pytest.approx(2.0 * risk, rel=1e-9)
    else:
        assert decision is None


def test_no_short_when_disabled():
    strat = TrendPullbackStrategy(allow_short=False)
    close = np.concatenate([np.linspace(150, 100, 80), np.linspace(100, 108, 12)])
    bars = _bars_from_close(close)
    decision = strat.evaluate(bars)
    assert decision is None or decision.side is Side.LONG


def test_strategy_is_deterministic():
    strat = TrendPullbackStrategy()
    close = 100 + np.cumsum(np.random.default_rng(9).normal(0, 1, 300))
    bars = _bars_from_close(close)
    d1 = strat.evaluate(bars)
    d2 = strat.evaluate(bars)
    assert d1 == d2
