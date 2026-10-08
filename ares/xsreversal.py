"""Cross-sectional short-term reversal: a FAST (high-bet-count) strategy.

Why this shape. Strategy quality = (edge per bet) * sqrt(bets per year). Trend
following makes ~25 bets/yr, so sqrt(25)=5 caps its quality near 0.5 whatever
the tuning -- which is exactly the 0.49 measured in ares/factors.py. Rebalancing
hourly across a wide universe makes ~8,760 bets/yr, so sqrt(N) is ~94 and a
per-bet edge nearly twenty times smaller reaches the quality (~4) needed to earn
real money inside a 6% account drawdown limit.

The signal (documented: Lehmann 1990, Lo & MacKinlay 1990, and the basis of much
statistical arbitrage). Crypto assets co-move strongly on a common market
factor. Measure each asset's return over a short lookback, subtract the
cross-sectional mean to strip that common factor out, and what remains is the
idiosyncratic move. Short the assets that diverged upward, buy those that
diverged downward, in equal dollars so the book stays market-neutral.

The thing that decides it is COST, not signal. Turnover scales with bet count:
rebalancing hourly with 50% turnover at 10bp round-trip burns ~438%/yr in fees.
So this module reports the GROSS edge and the cost it can bear, rather than
assuming a fee level -- the question is whether per-bet edge clears per-bet cost.

Everything routes through the audited Ledger, so equity is always
cash + sum(position * price) and no round-trip profit can be booked directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .ledger import Ledger


@dataclass
class ReversalResult:
    ledger: Ledger
    gross_return_pct: float      # before costs, annualised
    fees_paid: float
    turnover_per_rebalance: float
    n_rebalances: int
    bets_per_year: float


def run_xs_reversal(px: pd.DataFrame, *, lookback: int = 1, hold: int = 1,
                    top_k: int = 5, cost_bps: float = 0.0,
                    capital: float = 10_000.0,
                    bars_per_year: int = 24 * 365,
                    min_universe: int = 8,
                    min_sigma: float = 0.0,
                    sigma_window: int = 168) -> ReversalResult:
    """Short recent relative winners, buy relative losers; dollar-neutral.

    lookback: bars used to measure the idiosyncratic move.
    hold:     bars between rebalances (1 = every bar).
    top_k:    assets on each side. Smaller k = more extreme signal, more
              turnover per dollar deployed.
    cost_bps: round-trip cost in basis points of traded notional.
    """
    cols = list(px.columns)
    P = px.to_numpy(dtype=float)
    stamps = px.index.astype("datetime64[ms]").astype("int64").to_numpy()
    led = Ledger(capital)
    cost_rate = cost_bps / 1e4
    n = len(cols)
    turnover_frac = 0.0
    rebalances = 0
    last_ts = int(stamps[lookback]) if len(stamps) > lookback else 0

    for i in range(lookback, len(stamps)):
        ts = int(stamps[i])
        row = P[i]
        prev = P[i - lookback]
        live = np.isfinite(row) & np.isfinite(prev) & (row > 0) & (prev > 0)
        if live.sum() >= min_universe and (i - lookback) % hold == 0:
            r = np.full(n, np.nan)
            r[live] = row[live] / prev[live] - 1.0
            # strip the common market factor: what is left is idiosyncratic
            r[live] -= np.nanmean(r[live])
            if min_sigma > 0.0:
                # SELECTIVITY -- the direct attack on the fee problem. Trading
                # every asset every bar collects a tiny edge (2.13bp) against a
                # full fee (15bp retail). Requiring a dislocation of at least
                # min_sigma leaves the fee unchanged while raising the edge per
                # bet, so fewer and larger bets can clear a cost that constant
                # trading cannot. Sigma is the trailing cross-sectional spread
                # of these same demeaned moves, using past bars only.
                lo = max(lookback, i - sigma_window)
                hist = (P[lo:i] / np.where(P[lo - lookback:i - lookback] > 0,
                                           P[lo - lookback:i - lookback], np.nan) - 1.0)
                with np.errstate(invalid="ignore"):
                    hist = hist - np.nanmean(hist, axis=1, keepdims=True)
                sd = np.nanstd(hist)
                if not np.isfinite(sd) or sd <= 0:
                    sd = np.inf
                eligible = live & (np.abs(np.nan_to_num(r)) >= min_sigma * sd)
            else:
                eligible = live
            order = np.argsort(np.where(eligible, r, np.nan))
            valid = [j for j in order if eligible[j]]
            k = min(top_k, len(valid) // 2)
            longs = valid[:k]            # fell most vs the basket -> buy
            shorts = valid[-k:]          # rose most vs the basket -> short
            # Size off CURRENT equity, not the starting capital. Sizing off
            # starting capital holds notional fixed while equity falls, so
            # effective leverage grows as you lose -- a death spiral that
            # manufactured -100% results even with zero fees.
            equity_now = led.equity() if led.curve else capital
            if equity_now <= 0:
                break
            per = (equity_now / (2 * k)) if k else 0.0
            target = {c: 0.0 for c in cols}
            for j in longs:
                target[cols[j]] = per / row[j]
            for j in shorts:
                target[cols[j]] = -per / row[j]
            rebal_notional = 0.0
            for j in range(n):
                c = cols[j]
                if not np.isfinite(row[j]) or row[j] <= 0:
                    continue
                dq = target[c] - led.pos.get(c, 0.0)
                if abs(dq) > 1e-15:
                    notional = abs(dq) * float(row[j])
                    rebal_notional += notional
                    led.trade(ts, c, float(dq), float(row[j]),
                              cost=notional * cost_rate)
            # Turnover must be scale-free: accumulate it as a fraction of the
            # equity AT THE TIME of the trade. Dividing summed raw notional by
            # the STARTING capital reported 1,156,298% per rebalance once the
            # book compounded, which in turn zeroed out the breakeven figure.
            # Count a rebalance only when it actually traded. With selectivity
            # on, most bars have nothing eligible; counting those as bets would
            # inflate bets_per_year and deflate turnover-per-bet, corrupting the
            # per-bet breakeven that decides tradeability.
            if rebal_notional > 0.0:
                turnover_frac += rebal_notional / equity_now
                rebalances += 1
        marks = {cols[j]: float(row[j]) for j in range(n)
                 if np.isfinite(row[j]) and row[j] > 0}
        last_ts = ts
        if marks:
            eq = led.mark(ts, marks)
            if eq <= 0:
                break

    # Annualise over the span ACTUALLY traded. Using the full panel span after
    # an early break spread a ruin loss across 5.7 years and divided the bet
    # count by the wrong period, which is what produced "2 bets/yr" for a
    # configuration that rebalances every 72 bars.
    span_yr = (last_ts - stamps[lookback]) / 86_400_000 / 365.25
    eq0, eq1 = capital, led.equity()
    # Guard ruin: a book that goes to zero or negative has no meaningful
    # annualised rate, and ** on a negative base yields NaN rather than failing
    # loudly, which would quietly poison a results table.
    gross_mult = (eq1 + led.fees_paid) / eq0
    gross = (gross_mult ** (1 / span_yr) - 1) if (span_yr > 0 and gross_mult > 0) else -1.0
    return ReversalResult(
        ledger=led,
        gross_return_pct=gross * 100,
        fees_paid=led.fees_paid,
        turnover_per_rebalance=(turnover_frac / rebalances) if rebalances else 0.0,
        n_rebalances=rebalances,
        bets_per_year=(rebalances / span_yr) if span_yr > 0 else 0.0)


def breakeven_from(r: ReversalResult) -> float:
    """Round-trip cost (bp) at which the gross edge is exactly consumed.

    Takes an ALREADY-COMPUTED zero-cost result instead of re-running the
    backtest. The sweep was doing three full passes per configuration where two
    suffice, and at ~50k bars x 20 assets that third pass alone pushed the whole
    sweep past its time budget, so it produced nothing at all.

    This is the number that decides viability -- compare it against what can
    actually be traded (taker ~10bp round trip, maker ~2bp, VIP maker ~0).
    """
    if r.n_rebalances == 0 or r.turnover_per_rebalance <= 0 or r.bets_per_year <= 0:
        return 0.0
    gross_mult = 1.0 + r.gross_return_pct / 100.0
    if gross_mult <= 0:
        return 0.0
    # Compare like with like, PER BET. Dividing the COMPOUNDED annual rate by
    # SIMPLE annual turnover overstated this ~3x (3.99bp where the truth is
    # 1.36bp) and contradicted the module's own net-of-cost result, which came
    # out at -58.4%/yr for a configuration the breakeven called tradeable.
    edge_per_bet = gross_mult ** (1.0 / r.bets_per_year) - 1.0
    return (edge_per_bet / r.turnover_per_rebalance) * 1e4


def breakeven_cost_bps(px: pd.DataFrame, **kw) -> float:
    """Convenience wrapper: one zero-cost run, then derive breakeven from it."""
    return breakeven_from(run_xs_reversal(px, cost_bps=0.0, **kw))
