"""Pure numerical indicators.

Every function takes plain numpy arrays and returns a numpy array of the
same length (leading positions are NaN until the indicator has enough
data). No I/O, no globals, no randomness -> trivially unit-testable and
identical in backtest and live.
"""
from __future__ import annotations

import numpy as np


def ema(values: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average (recursive, adjust=False convention)."""
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if values.size == 0:
        return out
    alpha = 2.0 / (span + 1.0)
    out[0] = values[0]
    for i in range(1, values.size):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def sma(values: np.ndarray, period: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if values.size < period:
        return out
    cumsum = np.cumsum(np.insert(values, 0, 0.0))
    out[period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI."""
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if values.size <= period:
        return out
    delta = np.diff(values)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = gain[:period].mean()
    avg_loss = loss[:period].mean()

    def rsi_val(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = rsi_val(avg_gain, avg_loss)
    for i in range(period + 1, values.size):
        avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        out[i] = rsi_val(avg_gain, avg_loss)
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's Average True Range."""
    tr = true_range(high, low, close)
    out = np.full_like(tr, np.nan)
    if tr.size < period:
        return out
    out[period - 1] = tr[:period].mean()
    for i in range(period, tr.size):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out
