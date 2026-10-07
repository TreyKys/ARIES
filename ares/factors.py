"""Multi-factor systematic futures portfolio, through the audited ledger.

One signal is not a strategy. Real systematic futures funds run several
weakly-correlated factors together, because the portfolio Sharpe of N
uncorrelated factors each at S is roughly S*sqrt(N). Time-series momentum alone
measured +0.42 (t=2.06, 26yr) here, which is marginal; the question this module
answers is whether combining documented factors gets meaningfully above that.

Every factor is taken from the published literature with its parameters fixed
in advance -- there is nothing tuned here, because tuning until a number looked
good is what produced three phantom strategies earlier in this project.

    TSMOM     sign of trailing 12-month return            (Moskowitz/Ooi/Pedersen)
    XSMOM     cross-sectional: long top third of trailing 12m, short bottom third
              (Jegadeesh/Titman, applied across futures)
    REVERSAL  short-term reversal: against the trailing 1-month return
              (Lehmann, Lo/MacKinlay)
    BREAKOUT  Donchian channel position, the classic trend-following rule

All are volatility-scaled per market so no single market dominates, and all are
delta-sized off a constant risk budget rather than fixed notional.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .ledger import Ledger

VOL_WINDOW = 60
REBALANCE_DAYS = 21


def signal_matrix(px: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Target weight per market in [-1, 1]; NaN where not yet tradeable."""
    if kind == "multimom":
        # Blend momentum across horizons rather than betting the whole signal on
        # one lookback. Standard in the literature (a 12-month lookback is an
        # arbitrary single point on a continuum) and it costs nothing extra to
        # hold, since the positions net before trading.
        hs = (21, 63, 126, 252)
        acc = None
        for h in hs:
            sg = np.sign(px / px.shift(h) - 1.0)
            acc = sg if acc is None else acc + sg
        return (acc / float(len(hs))).where(~px.shift(max(hs)).isna())
    if kind == "tsmom":
        tr = px / px.shift(252) - 1.0
        return np.sign(tr)
    if kind == "xsmom":
        tr = px / px.shift(252) - 1.0
        rank = tr.rank(axis=1, pct=True)
        out = pd.DataFrame(0.0, index=px.index, columns=px.columns)
        out = out.where(~tr.isna())
        out[rank >= 2.0 / 3.0] = 1.0
        out[rank <= 1.0 / 3.0] = -1.0
        return out.where(~tr.isna())
    if kind == "reversal":
        tr = px / px.shift(21) - 1.0
        return -np.sign(tr)
    if kind == "breakout":
        hi = px.rolling(100).max()
        lo = px.rolling(100).min()
        mid = (hi + lo) / 2.0
        span = (hi - lo).replace(0.0, np.nan)
        return (2.0 * (px - mid) / span).clip(-1.0, 1.0)
    raise ValueError(kind)


def run_factor(px: pd.DataFrame, kinds: Sequence[str], *,
               capital: float = 100_000.0, risk_budget: float = 0.02,
               cost_bps: float = 10.0, vol_floor: float = 0.04,
               max_notional_frac: float = 0.50,
               target_markets: int = 24,
               rebalance_days: int = REBALANCE_DAYS,
               vol_target: float = 0.0,
               vol_target_window: int = 60,
               vol_scale_cap: float = 2.0) -> Ledger:
    """Equal-weight blend of `kinds`, rebalanced monthly, marked daily."""
    rets = px.pct_change()
    # Holidays are forward-filled so calendars align, creating runs of identical
    # prices. Those exact-zero returns drag rolling vol toward zero and make
    # 1/vol sizing explode, so mask them out of the risk estimate.
    vol = (rets.where(rets != 0.0)
           .rolling(VOL_WINDOW, min_periods=VOL_WINDOW // 2)
           .std() * np.sqrt(252)).clip(lower=vol_floor)

    sigs = [signal_matrix(px, k) for k in kinds]
    blend = sum(s.fillna(0.0) for s in sigs) / float(len(sigs))
    valid = sum((~s.isna()).astype(float) for s in sigs) > 0

    cols = list(px.columns)
    P = px.to_numpy(dtype=float)
    V = vol.to_numpy(dtype=float)
    W = blend.to_numpy(dtype=float)
    OK = valid.to_numpy()
    stamps = px.index.astype("datetime64[ms]").astype("int64").to_numpy()

    led = Ledger(capital)
    start = 253
    cost_rate = cost_bps / 1e4
    n = len(cols)
    own_rets: List[float] = []
    prev_eq: Optional[float] = None

    for i in range(start, len(stamps)):
        ts = int(stamps[i])
        prow, vrow, wrow, ok = P[i], V[i], W[i], OK[i]
        if (i - start) % rebalance_days == 0:
            live = ok & np.isfinite(prow) & np.isfinite(vrow) & (vrow > 0) & (prow > 0)
            n_live = max(int(live.sum()), 1)
            scaled = risk_budget * capital * np.sqrt(target_markets / n_live)
            if vol_target > 0 and len(own_rets) >= vol_target_window // 2:
                # Volatility management (Moreira & Muir 2017): scale exposure
                # inversely to the strategy's OWN recent realised volatility.
                # Uses only past returns, and is capped so a quiet stretch
                # cannot talk the book into unbounded size.
                w = own_rets[-vol_target_window:]
                mu = sum(w) / len(w)
                sd = (sum((x - mu) ** 2 for x in w) / max(len(w) - 1, 1)) ** 0.5
                rv = sd * np.sqrt(252)
                if rv > 1e-9:
                    scaled *= float(min(vol_target / rv, vol_scale_cap))
            with np.errstate(invalid="ignore", divide="ignore"):
                tgt = wrow * scaled / (vrow * prow)
                cap = (max_notional_frac * capital) / prow
                tgt = np.clip(tgt, -cap, cap)
            tgt = np.where(live, tgt, 0.0)
            for j in range(n):
                dq = tgt[j] - led.pos.get(cols[j], 0.0)
                if abs(dq) > 1e-12 and live[j]:
                    p = float(prow[j])
                    led.trade(ts, cols[j], float(dq), p, cost=abs(dq) * p * cost_rate)
        eq = led.mark(ts, {cols[j]: float(prow[j]) for j in range(n)
                           if np.isfinite(prow[j]) and prow[j] > 0})
        if prev_eq and prev_eq > 0:
            own_rets.append(eq / prev_eq - 1.0)
        prev_eq = eq
        if eq <= 0:
            break
    return led
