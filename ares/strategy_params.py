"""Strategy parameters, split into their own module so both the strategy
and the feature builder can import them without a cycle."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrendPullbackParams:
    ema_fast: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    rsi_long_max: float = 45.0
    rsi_short_min: float = 55.0
    atr_period: int = 14
    atr_mult: float = 1.5
    reward_multiple: float = 2.0
    allow_short: bool = False
    # optional intelligence gates (only applied when the feature is present)
    ml_min_win_prob: float = 0.0     # skip trades below this model probability
    sentiment_veto: float = 1.1      # skip longs when sentiment below -x / shorts above +x (>1 disables)
