"""Feature bundle: all inputs a strategy reads, precomputed once.

Indicators are computed vectorised over the whole series a single time
(each value is causal -- it depends only on data at or before its own
index -- so precomputing and then reading index ``i`` is identical to
recomputing on ``bars[:i+1]``, but O(n) instead of O(n^2)).

This is also the single, clearly-defined slot where non-deterministic
intelligence enters the deterministic core, and only as plain numbers:

    ml_win_prob : per-bar P(win) from a trained, frozen ML model
    sentiment   : per-bar score in [-1, 1] from the async LLM sidecar
    event_risk  : per-bar bool, True inside a macro news blackout

Any of these may be ``None``; the strategy treats missing inputs as
neutral, so the core runs identically with or without them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import indicators
from .strategy_params import TrendPullbackParams


@dataclass
class FeatureBundle:
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    ema_fast: np.ndarray
    ema_slow: np.ndarray
    rsi: np.ndarray
    atr: np.ndarray
    # optional intelligence, injected off the hot path (may be None)
    ml_win_prob: Optional[np.ndarray] = None
    sentiment: Optional[np.ndarray] = None
    event_risk: Optional[np.ndarray] = None

    def __len__(self) -> int:
        return int(self.close.size)


def build_features(
    ts: np.ndarray, open_: np.ndarray, high: np.ndarray, low: np.ndarray,
    close: np.ndarray, volume: np.ndarray, params: TrendPullbackParams,
    *, ml_win_prob=None, sentiment=None, event_risk=None,
) -> FeatureBundle:
    return FeatureBundle(
        ts=ts, open=open_, high=high, low=low, close=close, volume=volume,
        ema_fast=indicators.ema(close, params.ema_fast),
        ema_slow=indicators.ema(close, params.ema_slow),
        rsi=indicators.rsi(close, params.rsi_period),
        atr=indicators.atr(high, low, close, params.atr_period),
        ml_win_prob=ml_win_prob, sentiment=sentiment, event_risk=event_risk,
    )
