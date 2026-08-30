import numpy as np

from ares import indicators


def test_ema_constant_series_is_constant():
    x = np.full(50, 5.0)
    out = indicators.ema(x, span=10)
    assert out.shape == x.shape
    assert np.allclose(out, 5.0)


def test_sma_known_values():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = indicators.sma(x, period=3)
    assert np.isnan(out[:2]).all()
    assert out[2] == 2.0 and out[3] == 3.0 and out[4] == 4.0


def test_rsi_bounds_and_uptrend():
    up = np.arange(1, 100, dtype=float)          # strictly increasing
    r = indicators.rsi(up, period=14)
    valid = r[~np.isnan(r)]
    assert valid.min() >= 0.0 and valid.max() <= 100.0
    assert valid[-1] > 99.0                        # pure uptrend -> RSI ~100


def test_atr_positive_and_length():
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 1, 100))
    high = close + 1.0
    low = close - 1.0
    a = indicators.atr(high, low, close, period=14)
    assert a.shape == close.shape
    valid = a[~np.isnan(a)]
    assert (valid > 0).all()


def test_indicators_are_deterministic():
    x = 100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 200))
    assert np.array_equal(indicators.ema(x, 20), indicators.ema(x, 20), equal_nan=True)
    assert np.array_equal(indicators.rsi(x, 14), indicators.rsi(x, 14), equal_nan=True)
