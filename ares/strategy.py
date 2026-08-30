"""Deterministic trading strategies.

A ``Strategy`` maps market history to an optional ``StrategyDecision``. It
is a pure function of the data handed to it: same data in -> same decision
out. It never sees the future (it only reads feature values at or before
the current index), never sizes positions (that is the risk layer's job),
and never calls the network or an LLM on the hot path.

The strategy consumes a precomputed ``FeatureBundle`` so a backtest over
N candles is O(N), not O(N^2). Optional ML/sentiment features in the
bundle are applied only when present; otherwise they are ignored.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np

from .features import FeatureBundle, build_features
from .strategy_params import TrendPullbackParams
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

    def prepare(self, bars: Bars) -> FeatureBundle: ...
    def signal_at(self, fb: FeatureBundle, i: int) -> Optional[StrategyDecision]: ...
    def evaluate(self, bars: Bars) -> Optional[StrategyDecision]: ...


@dataclass
class TrendPullbackStrategy:
    """Trade pullbacks in the direction of the trend.

    Long when the fast EMA is above the slow EMA (uptrend) and RSI has
    dipped (a pullback); ATR stop below, fixed reward-multiple target
    above. Short is the mirror and is off by default.

    A defensible baseline -- NOT asserted to be profitable. The
    backtester exists precisely to prove or reject it.
    """
    ema_fast: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    rsi_long_max: float = 45.0
    rsi_short_min: float = 55.0
    atr_period: int = 14
    atr_mult: float = 1.5
    reward_multiple: float = 2.0
    allow_short: bool = False
    ml_min_win_prob: float = 0.0
    sentiment_veto: float = 1.1
    # optional injected intelligence (per-bar arrays), set before prepare()
    ml_win_prob: Optional[np.ndarray] = field(default=None, repr=False)
    sentiment: Optional[np.ndarray] = field(default=None, repr=False)
    event_risk: Optional[np.ndarray] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.warmup = max(self.ema_slow, self.rsi_period, self.atr_period) + 2

    @property
    def params(self) -> TrendPullbackParams:
        return TrendPullbackParams(
            ema_fast=self.ema_fast, ema_slow=self.ema_slow,
            rsi_period=self.rsi_period, rsi_long_max=self.rsi_long_max,
            rsi_short_min=self.rsi_short_min, atr_period=self.atr_period,
            atr_mult=self.atr_mult, reward_multiple=self.reward_multiple,
            allow_short=self.allow_short, ml_min_win_prob=self.ml_min_win_prob,
            sentiment_veto=self.sentiment_veto,
        )

    def prepare(self, bars: Bars) -> FeatureBundle:
        return build_features(
            bars.ts, bars.open, bars.high, bars.low, bars.close, bars.volume,
            self.params, ml_win_prob=self.ml_win_prob,
            sentiment=self.sentiment, event_risk=self.event_risk,
        )

    def signal_at(self, fb: FeatureBundle, i: int) -> Optional[StrategyDecision]:
        if i < self.warmup - 1:
            return None
        f, s, r, a = fb.ema_fast[i], fb.ema_slow[i], fb.rsi[i], fb.atr[i]
        close = fb.close[i]
        if np.isnan(f) or np.isnan(s) or np.isnan(r) or np.isnan(a) or a <= 0:
            return None

        # macro news blackout (optional feature)
        if fb.event_risk is not None and bool(fb.event_risk[i]):
            return None

        meta = {"rsi": round(float(r), 2), "atr": round(float(a), 6)}

        side: Optional[Side] = None
        if f > s and r < self.rsi_long_max:
            side = Side.LONG
        elif self.allow_short and f < s and r > self.rsi_short_min:
            side = Side.SHORT
        if side is None:
            return None

        # optional sentiment veto (trade only with, not against, strong sentiment)
        if fb.sentiment is not None and self.sentiment_veto <= 1.0:
            snt = float(fb.sentiment[i])
            if side is Side.LONG and snt < -self.sentiment_veto:
                return None
            if side is Side.SHORT and snt > self.sentiment_veto:
                return None

        # optional ML meta-label filter (skip low-probability setups)
        if fb.ml_win_prob is not None and self.ml_min_win_prob > 0.0:
            p = float(fb.ml_win_prob[i])
            if not np.isnan(p) and p < self.ml_min_win_prob:
                return None
            meta["ml_win_prob"] = round(p, 3)

        if side is Side.LONG:
            stop = close - self.atr_mult * a
            risk = close - stop
            if risk <= 0:
                return None
            tp = close + self.reward_multiple * risk
            return StrategyDecision(Side.LONG, stop, tp,
                                    f"Uptrend pullback (RSI {r:.1f})", meta)
        else:
            stop = close + self.atr_mult * a
            risk = stop - close
            if risk <= 0:
                return None
            tp = close - self.reward_multiple * risk
            return StrategyDecision(Side.SHORT, stop, tp,
                                    f"Downtrend pullback (RSI {r:.1f})", meta)

    def evaluate(self, bars: Bars) -> Optional[StrategyDecision]:
        """Convenience: decision at the most recent bar (used in tests)."""
        if len(bars) < self.warmup:
            return None
        fb = self.prepare(bars)
        return self.signal_at(fb, len(bars) - 1)
