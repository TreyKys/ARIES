"""Deterministic trading strategies.

A ``Strategy`` maps market history to an optional ``StrategyDecision``.
It is a pure function of the bars handed to it: the same bars always
produce the same decision. It never sees the future (arrays end at the
current, just-closed candle), never sizes positions (that is the risk
layer's job), and never calls the network or an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

from . import indicators
from .types import Side, StrategyDecision


@dataclass(frozen=True)
class Bars:
    """A window of OHLCV as parallel numpy arrays (oldest -> newest)."""
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return int(self.close.size)


class Strategy(Protocol):
    warmup: int

    def evaluate(self, bars: Bars) -> Optional[StrategyDecision]:
        ...


@dataclass
class TrendPullbackStrategy:
    """Trade pullbacks in the direction of the trend.

    Long when the fast EMA is above the slow EMA (uptrend) and RSI has
    dipped into oversold territory (a pullback), then place an ATR stop
    below and a fixed reward-multiple target above. Short is the mirror
    image and is off by default.

    This is a standard, defensible baseline. It is NOT asserted to be
    profitable -- that is exactly what the backtester exists to find out.
    """
    ema_fast: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    rsi_long_max: float = 45.0    # long only when RSI has pulled back below this
    rsi_short_min: float = 55.0   # short only when RSI has popped above this
    atr_period: int = 14
    atr_mult: float = 1.5         # stop distance = atr_mult * ATR
    reward_multiple: float = 2.0  # take-profit distance = reward_multiple * stop distance
    allow_short: bool = False

    def __post_init__(self) -> None:
        self.warmup = max(self.ema_slow, self.rsi_period, self.atr_period) + 2

    def evaluate(self, bars: Bars) -> Optional[StrategyDecision]:
        if len(bars) < self.warmup:
            return None

        ema_fast = indicators.ema(bars.close, self.ema_fast)
        ema_slow = indicators.ema(bars.close, self.ema_slow)
        rsi = indicators.rsi(bars.close, self.rsi_period)
        atr = indicators.atr(bars.high, bars.low, bars.close, self.atr_period)

        f, s = ema_fast[-1], ema_slow[-1]
        r, a = rsi[-1], atr[-1]
        close = bars.close[-1]

        if np.isnan(f) or np.isnan(s) or np.isnan(r) or np.isnan(a) or a <= 0:
            return None

        meta = {"rsi": round(float(r), 2), "atr": round(float(a), 6),
                "ema_fast": float(f), "ema_slow": float(s)}

        # Long: uptrend + pullback
        if f > s and r < self.rsi_long_max:
            stop = close - self.atr_mult * a
            risk = close - stop
            if risk <= 0:
                return None
            tp = close + self.reward_multiple * risk
            return StrategyDecision(
                side=Side.LONG, stop_price=stop, take_profit_price=tp,
                reason=f"Uptrend pullback (RSI {r:.1f} < {self.rsi_long_max})",
                meta=meta,
            )

        # Short: downtrend + pullback (opt-in)
        if self.allow_short and f < s and r > self.rsi_short_min:
            stop = close + self.atr_mult * a
            risk = stop - close
            if risk <= 0:
                return None
            tp = close - self.reward_multiple * risk
            return StrategyDecision(
                side=Side.SHORT, stop_price=stop, take_profit_price=tp,
                reason=f"Downtrend pullback (RSI {r:.1f} > {self.rsi_short_min})",
                meta=meta,
            )

        return None
