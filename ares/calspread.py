"""Futures calendar-spread carry: the one carry source that survives inside a
SINGLE futures account (so it is prop-firm compatible).

Why this exists. A delta-neutral book earns nothing from price movement, only
carry (see ares/grid.py). Carry only survives if the two legs are DIFFERENT
instruments: a same-symbol long+short cancels funding exactly, which is why an
all-perp "hedged grid" is a guaranteed loss. A calendar spread is long one
expiry and short another -- different contracts, so the term-structure carry
does NOT cancel, while the position stays neutral to parallel moves in the
underlying.

The a priori economics (NOT fitted). Let F(T) be price as a function of
time-to-maturity. In backwardation F decreases in T, so as a contract ages its
maturity shortens and its price rolls UP; the front leg has the steepest local
slope and rolls fastest, so long-front/short-back gains. In contango the curve
increases in T, contracts roll DOWN, the front falls fastest, so short-front
gains. Hence the pre-specified rule:

    position = sign(C1 - C2)      long the front spread when backwardated

Methodology hazard this module exists to avoid. EIA C1..C4 are CONTINUOUS
series: when the front expires, C1 is relabelled to the next contract and jumps
by roughly -(C1-C2). That artificial jump is almost exactly MINUS the signal, so
attributing P&L to it manufactures an edge perfectly correlated with the signal.
Roll days are therefore identified from the deterministic exchange expiry
calendar (never from the size of the returns, which would be snooping), earn NO
price P&L, and are charged an explicit roll cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

BD = pd.offsets.BDay()


def cl_expiries(start: int, end: int) -> set:
    """NYMEX CL: trading ends 3 business days before the 25th calendar day of
    the month preceding delivery (25th rolled back to a business day first)."""
    out = set()
    for y in range(start, end + 1):
        for m in range(1, 13):
            ref = pd.Timestamp(y, m, 25)
            while ref.weekday() >= 5:
                ref -= pd.Timedelta(days=1)
            e = (ref - 3 * BD).normalize()
            out.add(e)
            out.add((e + BD).normalize())     # the relabelling lands next day
    return out


def ng_expiries(start: int, end: int) -> set:
    """NYMEX NG: trading ends 3 business days before the 1st of delivery."""
    out = set()
    for y in range(start, end + 1):
        for m in range(1, 13):
            e = (pd.Timestamp(y, m, 1) - 3 * BD).normalize()
            out.add(e)
            out.add((e + BD).normalize())
    return out


@dataclass
class SpreadResult:
    ann_return_pct: float
    ann_vol_pct: float
    sharpe: float
    max_drawdown_pct: float
    days: int
    turnover: int
    hit_rate_pct: float
    equity: pd.Series


def backtest_calspread(panel: pd.DataFrame, expiries: set, *,
                       cost_rt: float = 4e-4, signal: str = "carry",
                       near: str = "C1", far: str = "C2",
                       rng: Optional[np.random.Generator] = None) -> SpreadResult:
    """Hold `sign(near-far)` of the calendar spread, rolled on expiry.

    cost_rt: round-trip cost as a fraction of ONE leg's notional, covering both
      legs (commission + spread). ~4bps is conservative for CL at a prop firm.
    signal: 'carry' (pre-specified), 'inverted' or 'random' (placebos).
    """
    d = panel.dropna().copy()
    # Stable notional: trailing 1y median of the near leg. Avoids the April-2020
    # negative-price pathology that destroys percentage returns.
    notional = d[near].rolling(252, min_periods=20).median().abs().clip(lower=1.0)
    dollar = d[near].diff() - d[far].diff()        # P&L per 1 unit long spread
    r = (dollar / notional.shift(1)).dropna()

    slope = (d[near] - d[far]) / notional          # scale-free carry signal
    if signal == "carry":
        pos = np.sign(slope).shift(1)              # decided on yesterday's close
    elif signal == "inverted":
        pos = -np.sign(slope).shift(1)
    elif signal == "random":
        g = rng or np.random.default_rng(0)
        pos = pd.Series(g.choice([-1.0, 1.0], size=len(d)), index=d.index).shift(1)
    else:
        raise ValueError(signal)
    pos = pos.reindex(r.index).fillna(0.0)

    flagged = pd.Series([t.normalize() in expiries for t in r.index], index=r.index)
    # A daily DIFFERENCE is contaminated if EITHER endpoint is a relabelling
    # day: diff[t] = C1[t] - C1[t-1] straddles the switch, and the jump also
    # leaks into diff[t+1]. Excluding only the roll day itself leaves that leak,
    # which is enough to manufacture a signal-correlated edge on its own.
    isroll = flagged | flagged.shift(1).fillna(False).astype(bool)
    pnl = (pos * r).where(~isroll, 0.0)            # no P&L across a relabelling

    flips = pos.diff().abs().fillna(0.0) / 2.0     # 1.0 = full reversal
    costs = flips * cost_rt + isroll.astype(float) * cost_rt   # flip + monthly roll
    net = pnl - costs

    eq = (1.0 + net).cumprod()
    days = len(net)
    yrs = days / 252.0
    ann = (eq.iloc[-1] ** (1 / yrs) - 1) * 100 if yrs > 0 and eq.iloc[-1] > 0 else -99.0
    vol = net.std() * np.sqrt(252) * 100
    sharpe = (net.mean() * 252) / (net.std() * np.sqrt(252)) if net.std() > 0 else 0.0
    dd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    traded = net[(pos != 0) & (~isroll)]
    hit = 100.0 * (traded > 0).mean() if len(traded) else 0.0
    return SpreadResult(ann, vol, sharpe, dd, days, int(flips.sum()), hit, eq)
