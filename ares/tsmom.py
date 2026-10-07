"""Time-series momentum (trend following) through the audited ledger.

This is deliberately NOT a strategy invented here. It is the published
time-series momentum rule (Moskowitz, Ooi & Pedersen 2012), whose parameters
come from the literature rather than from fitting this data:

    signal     sign of the trailing 12-month (252 trading day) return
    sizing     scale each market to a constant volatility budget
    rebalance  monthly
    universe   diversified across equities, FX, commodities and rates

Taking the parameters as given is what makes this testable. Every earlier
strategy in this repo was tuned until a number looked good, which is why the
numbers did not survive. Here there is nothing to tune, so the only question
the data has to answer is whether the documented effect is present and large
enough -- including the well-known post-2010 degradation.

Volatility targeting is not an optimisation, it is what makes a diversified
basket meaningful: without it natural gas would dominate the portfolio and the
result would just be a bet on one market.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .ledger import Ledger, Stats, summarise

LOOKBACK = 252          # 12 months, per the literature
VOL_WINDOW = 60         # 3 months, for the risk estimate
REBALANCE_DAYS = 21     # monthly


def build_panel(names: Sequence[str], folder: str = "data/daily") -> pd.DataFrame:
    """Close prices aligned on a common calendar, forward-filled over holidays."""
    cols = {}
    for n in names:
        d = pd.read_csv(f"{folder}/{n}.csv")
        s = pd.Series(d["close"].values,
                      index=pd.to_datetime(d["ts"], unit="ms")).sort_index()
        cols[n] = s[~s.index.duplicated(keep="last")]
    px = pd.DataFrame(cols).sort_index()
    return px.ffill()


def run_tsmom(px: pd.DataFrame, *, capital: float = 100_000.0,
              risk_budget: float = 0.02, cost_bps: float = 10.0,
              lookback: int = LOOKBACK, vol_window: int = VOL_WINDOW,
              rebalance_days: int = REBALANCE_DAYS,
              signal: str = "momentum",
              rng: Optional[np.random.Generator] = None) -> Ledger:
    """Trade the basket and return the LEDGER, so P&L is auditable.

    risk_budget: target annualised vol contribution per market, as a fraction
      of capital. Dollar position = risk_budget * capital / vol_market, so a
      20%-vol market gets a 10% position at a 2% budget.
    signal: 'momentum' (the rule), 'random' or 'inverted' (placebo controls).
    """
    rets = px.pct_change()
    vol = rets.rolling(vol_window).std() * np.sqrt(252)
    trail = px / px.shift(lookback) - 1.0

    led = Ledger(capital)
    dates = px.index
    start = max(lookback, vol_window) + 1
    g = rng or np.random.default_rng(0)
    cost_rate = cost_bps / 1e4

    target: Dict[str, float] = {}
    for i in range(start, len(dates)):
        t = dates[i]
        ts = int(t.value // 1_000_000)
        row = px.iloc[i]

        if (i - start) % rebalance_days == 0:
            for m in px.columns:
                p, v, tr = row[m], vol[m].iloc[i], trail[m].iloc[i]
                if not np.isfinite(p) or not np.isfinite(v) or not np.isfinite(tr) \
                        or v <= 0 or p <= 0:
                    target[m] = 0.0
                    continue
                if signal == "momentum":
                    s = 1.0 if tr > 0 else -1.0
                elif signal == "inverted":
                    s = -1.0 if tr > 0 else 1.0
                elif signal == "random":
                    s = float(g.choice([-1.0, 1.0]))
                else:
                    raise ValueError(signal)
                target[m] = s * (risk_budget * capital) / (v * p)
            for m, tgt in target.items():
                cur = led.pos.get(m, 0.0)
                dq = tgt - cur
                p = row[m]
                if abs(dq) > 1e-12 and np.isfinite(p) and p > 0:
                    led.trade(ts, m, dq, float(p), cost=abs(dq) * float(p) * cost_rate)

        led.mark(ts, {m: float(row[m]) for m in px.columns
                      if np.isfinite(row[m]) and row[m] > 0})
    return led


def stats(led: Ledger) -> Stats:
    return summarise(led)
