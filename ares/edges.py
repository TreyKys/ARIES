"""Candidate edges, each specified in advance from the literature.

Why this module exists. Breadth was tested and failed; speed was tested and
failed (docs/UNIVERSE_WIDENING.md, docs/HOURLY_REVERSAL_RETEST.md). What is
left is INDEPENDENCE: combining uncorrelated return streams. The arithmetic is
unforgiving -- k streams of equal Sharpe s combine to s*sqrt(k), so reaching
1.2 from 0.54 takes roughly five independent edges, not one. A negatively
correlated pair does better: two 0.54 edges at r=-0.3 combine to 0.91.

So the output that matters here is the CORRELATION MATRIX between candidate
return streams, not any single Sharpe.

DISCIPLINE. Every signal below is written to its published specification and
committed before measurement. No lookback is tuned, no variant is kept because
it scored well. Each takes a trailing window and returns target weights in
[-1, 1] for the LAST bar of that window, using only data inside it -- so a
signal cannot see its own future.
"""
from __future__ import annotations

from typing import Callable, Dict

import numpy as np
import pandas as pd

# Longest history any signal needs, in trading days: value looks back five
# years and skips the most recent one.
MAX_LOOKBACK = 252 * 6 + 5


def _long_short(score: pd.Series, top_k: int, *, long_high: bool) -> pd.Series:
    """Long the extreme end of a cross-sectional score, short the other.

    Demeaning first strips the common market factor, so what is ranked is each
    market's position RELATIVE to the basket -- the part a cross-sectional bet
    can actually capture.
    """
    s = score.replace([np.inf, -np.inf], np.nan).dropna()
    w = pd.Series(0.0, index=score.index)
    if len(s) < 6:
        return w
    s = s - s.mean()
    order = s.sort_values().index
    k = min(top_k, len(order) // 2)
    if k == 0:
        return w
    w.loc[order[-k:]] = 1.0 if long_high else -1.0
    w.loc[order[:k]] = -1.0 if long_high else 1.0
    return w


def _ret(win: pd.DataFrame, start: int, end: int = 1) -> pd.Series:
    """Return from `start` bars ago to `end` bars ago (1 = the last bar)."""
    if len(win) < start + 1:
        return pd.Series(np.nan, index=win.columns)
    return win.iloc[-end] / win.iloc[-start] - 1.0


# --- the candidates --------------------------------------------------------

def trend(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Time-series momentum: sign of the trailing 12-month return.
    Moskowitz, Ooi & Pedersen (2012). The book's existing trend leg."""
    return np.sign(_ret(win, 253)).fillna(0.0)


def xsrev(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """One-day cross-sectional reversal. Lehmann (1990), Lo & MacKinlay
    (1990). The book's existing reversal leg and its only real earner."""
    return _long_short(_ret(win, 2), top_k, long_high=False)


def value(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Long-horizon reversal: minus the 5-year return, SKIPPING the most
    recent 12 months so it does not overlap momentum. Asness, Moskowitz &
    Pedersen (2013), 'Value and Momentum Everywhere'. Expected to be
    NEGATIVELY correlated with trend, which is worth more than zero."""
    return _long_short(_ret(win, 252 * 6 + 1, 253), top_k, long_high=False)


def xsmom(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Cross-sectional momentum, 12 months skipping the most recent one.
    Jegadeesh & Titman (1993). Distinct from time-series trend: this ranks
    markets against each other rather than against zero."""
    return _long_short(_ret(win, 274, 22), top_k, long_high=True)


def tsrev(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """One-month time-series reversal: fade each market's own last month,
    irrespective of the others. Different bet from xsrev, which is relative."""
    return (-np.sign(_ret(win, 22))).fillna(0.0)


def lowvol(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Betting against beta: long the calmest markets, short the wildest.
    Frazzini & Pedersen (2014). A risk-based premium, not a price-pattern
    one, so there is reason to expect it to be independent of the rest."""
    if len(win) < 253:
        return pd.Series(0.0, index=win.columns)
    v = win.iloc[-253:].pct_change().std()
    return _long_short(v, top_k, long_high=False)


def skew(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Lottery preference: investors overpay for positive skew, so short the
    most positively skewed and buy the most negatively skewed.
    Bali, Cakici & Whitelaw (2011)."""
    if len(win) < 253:
        return pd.Series(0.0, index=win.columns)
    s = win.iloc[-253:].pct_change().skew()
    return _long_short(s, top_k, long_high=False)


def seasonal(win: pd.DataFrame, top_k: int = 3) -> pd.Series:
    """Same-calendar-month historical mean return, from PRIOR years only.
    Heston & Sadka (2008). Included because it is mechanically unrelated to
    everything above -- and flagged as the most overfit-prone of the slate,
    so a good score here deserves the most suspicion."""
    if len(win) < 252 * 3:
        return pd.Series(0.0, index=win.columns)
    r = win.pct_change()
    month = win.index[-1].month
    # strictly prior years: exclude the current one
    prior = r[(r.index.month == month) & (r.index.year < win.index[-1].year)]
    if len(prior) < 40:
        return pd.Series(0.0, index=win.columns)
    return _long_short(prior.mean(), top_k, long_high=True)


EDGES: Dict[str, Callable[..., pd.Series]] = {
    "trend": trend, "xsrev": xsrev, "value": value, "xsmom": xsmom,
    "tsrev": tsrev, "lowvol": lowvol, "skew": skew, "seasonal": seasonal,
}
