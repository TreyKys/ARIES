"""Statistical arbitrage: market-neutral pairs trading.

Two cointegrated assets drift apart and snap back. We fade the spread:
when asset A gets expensive relative to B (spread z-score high), short A /
long B in equal dollars; unwind as it reverts. Because both legs are held
at once, broad market direction cancels -- the edge is the *relationship*,
not a price prediction. That is why it is low-drawdown and does not decay
like a directional signal.

Everything is causal (rolling hedge ratio and z-score use only data up to
the current bar) and costs are charged on all four fills per round trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StatArbParams:
    lookback: int = 100          # bars for rolling hedge ratio + z-score
    entry_z: float = 2.0         # enter when |z| exceeds this
    exit_z: float = 0.5          # unwind when |z| falls below this
    stop_z: float = 4.0          # bail if the spread blows out further
    max_hold: int = 240          # force-exit after this many bars (no reversion)
    cost_roundtrip: float = 0.002  # fees+slippage across all 4 legs, as fraction of capital


@dataclass
class PairResult:
    a: str
    b: str
    trades: List[float] = field(default_factory=list)   # per-trade returns (net)
    equity_curve: List[Tuple[int, float]] = field(default_factory=list)

    @property
    def metrics(self) -> dict:
        t = self.trades
        n = len(t)
        if n == 0:
            return {"n": 0, "win_rate": 0.0, "pf": 0.0, "mean_ret": 0.0,
                    "total_ret_pct": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0}
        wins = [x for x in t if x > 0]
        gp = sum(wins); gl = -sum(x for x in t if x <= 0)
        eq = np.array([e for _, e in self.equity_curve]) if self.equity_curve else np.array([1.0])
        peak = np.maximum.accumulate(eq)
        max_dd = float(np.max((peak - eq) / peak)) * 100 if eq.size else 0.0
        arr = np.array(t)
        sharpe = float(arr.mean() / arr.std() * np.sqrt(len(arr))) if arr.std() > 0 else 0.0
        return {
            "n": n, "win_rate": len(wins) / n,
            "pf": (gp / gl) if gl > 0 else float("inf"),
            "mean_ret": float(arr.mean()),
            "total_ret_pct": (eq[-1] - 1.0) * 100 if eq.size else 0.0,
            "sharpe": sharpe, "max_dd_pct": max_dd,
        }


def align(series: Dict[str, Sequence]) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Inner-join candle lists by timestamp -> aligned close arrays."""
    frames = {}
    for sym, candles in series.items():
        frames[sym] = pd.Series({c.ts: c.close for c in candles})
    df = pd.DataFrame(frames).dropna()
    ts = df.index.to_numpy()
    return ts, {c: df[c].to_numpy() for c in df.columns}


def rolling_zscore(a: np.ndarray, b: np.ndarray, lookback: int
                   ) -> Tuple[np.ndarray, np.ndarray]:
    """Causal rolling hedge ratio (log prices) and spread z-score."""
    la, lb = np.log(a), np.log(b)
    sa, sb = pd.Series(la), pd.Series(lb)
    cov = sa.rolling(lookback).cov(sb)
    var = sb.rolling(lookback).var()
    beta = (cov / var).to_numpy()
    spread = la - beta * lb
    ss = pd.Series(spread)
    z = ((ss - ss.rolling(lookback).mean()) / ss.rolling(lookback).std()).to_numpy()
    return z, beta


def half_life(spread: np.ndarray) -> float:
    """Mean-reversion half-life (bars) via an AR(1) fit on the spread.

    dS_t = lambda * S_{t-1} + c.  half-life = -ln(2)/lambda for lambda<0.
    Returns inf if the spread is not mean-reverting.
    """
    s = spread[~np.isnan(spread)]
    if s.size < 20:
        return float("inf")
    lag = s[:-1]
    ds = np.diff(s)
    x = np.column_stack([lag, np.ones_like(lag)])
    try:
        lam, _c = np.linalg.lstsq(x, ds, rcond=None)[0]
    except Exception:
        return float("inf")
    if lam >= 0:
        return float("inf")
    return float(-np.log(2) / lam)


def static_spread(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, float]:
    """Full-sample OLS hedge ratio and log-price spread (for selection only)."""
    la, lb = np.log(a), np.log(b)
    beta = np.cov(la, lb)[0, 1] / np.var(lb)
    return la - beta * lb, float(beta)


def backtest_pair(name_a: str, name_b: str, a: np.ndarray, b: np.ndarray,
                  ts: np.ndarray, p: StatArbParams) -> PairResult:
    z, _beta = rolling_zscore(a, b, p.lookback)
    res = PairResult(a=name_a, b=name_b)
    equity = 1.0
    res.equity_curve.append((int(ts[0]), equity))

    pos = 0          # +1 long spread (long A/short B), -1 short spread, 0 flat
    entry_i = -1
    for i in range(p.lookback + 1, len(a)):
        zi = z[i]
        if np.isnan(zi):
            continue
        if pos == 0:
            if zi >= p.entry_z:
                pos, entry_i = -1, i          # spread high -> short A, long B
            elif zi <= -p.entry_z:
                pos, entry_i = +1, i          # spread low -> long A, short B
        else:
            held = i - entry_i
            revert = abs(zi) <= p.exit_z
            blow = abs(zi) >= p.stop_z
            timeout = held >= p.max_hold
            if revert or blow or timeout:
                ra = a[i] / a[entry_i] - 1.0
                rb = b[i] / b[entry_i] - 1.0
                # long spread (pos=+1): long A, short B -> +ra - rb ; short spread mirrors
                gross = pos * (ra - rb) * 0.5   # dollar-neutral, half capital per leg
                net = gross - p.cost_roundtrip
                equity *= (1.0 + net)
                res.trades.append(net)
                res.equity_curve.append((int(ts[i]), equity))
                pos = 0
    return res
