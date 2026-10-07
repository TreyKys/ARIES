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
TARGET_MARKETS = 24     # universe size the risk budget is calibrated to


def build_panel(names: Sequence[str], folder: str = "data/daily") -> pd.DataFrame:
    """Close prices aligned on a common calendar, forward-filled over holidays."""
    cols = {}
    for n in names:
        d = pd.read_csv(f"{folder}/{n}.csv")
        s = pd.Series(d["close"].values,
                      index=pd.to_datetime(d["ts"], unit="ms")).sort_index()
        # Yahoo stamps each market at its own LOCAL session time (SPX 14:30,
        # FX elsewhere). Aligning on raw timestamps builds a union index with
        # roughly one row per market per day -- 26,742 rows for 3 markets
        # instead of ~14,000 -- and forward-fills each market across the
        # others' stamps, manufacturing runs of identical prices. Those became
        # zero-return days that collapsed the rolling vol and blew up 1/vol
        # position sizing. Normalise to the calendar date first.
        s.index = s.index.normalize()
        cols[n] = s[~s.index.duplicated(keep="last")]
    px = pd.DataFrame(cols).sort_index()
    return px.ffill()


def run_tsmom(px: pd.DataFrame, *, capital: float = 100_000.0,
              risk_budget: float = 0.02, cost_bps: float = 10.0,
              lookback: int = LOOKBACK, vol_window: int = VOL_WINDOW,
              rebalance_days: int = REBALANCE_DAYS,
              signal: str = "momentum", vol_floor: float = 0.04,
              max_notional_frac: float = 0.50,
              rng: Optional[np.random.Generator] = None) -> Ledger:
    """Trade the basket and return the LEDGER, so P&L is auditable.

    risk_budget: target annualised vol contribution per market, as a fraction
      of capital. Dollar position = risk_budget * capital / vol_market, so a
      20%-vol market gets a 10% position at a 2% budget.
    vol_floor: minimum annualised vol used for sizing. Guards against
      forward-filled holidays collapsing the risk estimate.
    max_notional_frac: hard cap on any single market's notional.
    signal: 'momentum' (the rule), 'random' or 'inverted' (placebo controls).
    """
    rets = px.pct_change()
    # Holidays are forward-filled so calendars align, which creates runs of
    # IDENTICAL prices. Those produce exact-zero returns, which drag the rolling
    # vol toward zero, which makes 1/vol position sizing explode -- UST10 showed
    # 0.4%/yr vol implying a 246x leverage multiplier. A filled holiday is not
    # an observation of zero volatility, so mask exact zeros out of the risk
    # estimate. Genuine zero-return days are rare at daily resolution, and
    # dropping them biases vol slightly UP, i.e. toward smaller positions.
    rets_for_vol = rets.where(rets != 0.0)
    vol_df = (rets_for_vol.rolling(vol_window, min_periods=vol_window // 2)
              .std() * np.sqrt(252))
    vol_df = vol_df.clip(lower=vol_floor)
    trail_df = px / px.shift(lookback) - 1.0

    # Hoist everything into numpy: pandas scalar access inside a 14,000-day
    # loop over 24 markets dominates the runtime by orders of magnitude.
    cols = list(px.columns)
    P = px.to_numpy(dtype=float)
    V = vol_df.to_numpy(dtype=float)
    T = trail_df.to_numpy(dtype=float)
    # Unit-safe: this index is datetime64[ms], NOT nanoseconds, so dividing by
    # 1e6 destroys it. Cast to a known resolution before going to int.
    stamps = px.index.astype("datetime64[ms]").astype("int64").to_numpy()

    led = Ledger(capital)
    start = max(lookback, vol_window) + 1
    g = rng or np.random.default_rng(0)
    cost_rate = cost_bps / 1e4
    budget = risk_budget * capital
    n_mkt = len(cols)
    target = np.zeros(n_mkt)

    for i in range(start, len(stamps)):
        ts = int(stamps[i])
        prow, vrow, trow = P[i], V[i], T[i]

        if (i - start) % rebalance_days == 0:
            live = np.isfinite(prow) & np.isfinite(vrow) & np.isfinite(trow) \
                & (vrow > 0) & (prow > 0)
            if signal == "momentum":
                sgn = np.where(trow > 0, 1.0, -1.0)
            elif signal == "inverted":
                sgn = np.where(trow > 0, -1.0, 1.0)
            elif signal == "random":
                sgn = g.choice([-1.0, 1.0], size=n_mkt)
            else:
                raise ValueError(signal)
            # Scale the per-market budget by universe size. Markets phase in
            # as their history begins (1 live in 1970, 24 by 2026); a fixed
            # per-market budget would therefore make portfolio risk grow
            # mechanically over time (measured vol 3.6% -> 17.5%) and make
            # sub-period comparison meaningless. 1/sqrt(n) keeps aggregate
            # risk roughly constant, which is standard practice, not a fit.
            n_live = max(int(live.sum()), 1)
            scaled = budget * np.sqrt(TARGET_MARKETS / n_live)
            with np.errstate(invalid="ignore", divide="ignore"):
                tgt = sgn * scaled / (vrow * prow)
                # hard per-market notional cap: a risk limit any real system
                # has, and a backstop against a bad vol estimate
                cap = (max_notional_frac * capital) / prow
                tgt = np.clip(tgt, -cap, cap)
            target = np.where(live, tgt, 0.0)
            for j in range(n_mkt):
                cur = led.pos.get(cols[j], 0.0)
                dq = target[j] - cur
                if abs(dq) > 1e-12 and live[j]:
                    p = float(prow[j])
                    led.trade(ts, cols[j], float(dq), p,
                              cost=abs(dq) * p * cost_rate)

        eq = led.mark(ts, {cols[j]: float(prow[j]) for j in range(n_mkt)
                           if np.isfinite(prow[j]) and prow[j] > 0})
        if eq <= 0:
            # Ruin. A real account is liquidated here; continuing produces
            # meaningless returns on negative equity (the inverted placebo
            # reported -100%/yr at 549% vol by running past this point).
            break
    return led


def stats(led: Ledger) -> Stats:
    return summarise(led)
