"""Daily order ticket for the FX-majors reversal book, for MANUAL entry in MT5.

FundedNext's Stellar 2-Step rules: "EA usage is not permitted on account sizes
of $50,000 and above." So on a $100k account this software never trades. It
computes the book and prints exactly what to type into MetaTrader 5 -- pair,
side, lots, stop-loss -- and the trader places every order by hand. The book
rebalances once a day; it is about seven orders.

Two conventions are the whole risk of a manual ticket, so both are explicit:

  * The signal is computed on each currency's DOLLAR value (EUR, GBP, AUD,
    NZD as quoted; CAD, CHF, JPY inverted), because that is what makes the
    cross-sectional ranking a bet on currencies rather than on the dollar.
  * MT5 trades the pair as quoted. Being long CAD means SELLING USDCAD. A
    ticket that got this backwards would put on the exact opposite book, and
    the tests pin it.

Stops. FundedNext caps aggregate open risk on funded accounts at 3% of the
initial balance, counting stop-loss placement and floating losses; a first
breach forfeits that cycle's reward and a second cuts the cap to 1% for good.
Stops are sized so their combined risk stays inside a 2.5% budget, allocated
in proportion to each position's own volatility. The ticket reports how many
daily moves away the stops sit; inside 2.5, they will be hit routinely and
the vol target should come down.

Pure functions only, so all of it is testable without a broker or network.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

LOT = 100_000.0
# MT5 pair -> (currency the book holds, True if the pair is quoted USD-first)
PAIRS = {
    "EURUSD": ("EUR", False), "GBPUSD": ("GBP", False),
    "AUDUSD": ("AUD", False), "NZDUSD": ("NZD", False),
    "USDCAD": ("CAD", True), "USDCHF": ("CHF", True), "USDJPY": ("JPY", True),
}
RISK_BUDGET = 0.025          # under FundedNext's 3% open-risk cap


@dataclass
class FxOrder:
    pair: str
    side: str            # BUY / SELL the pair as quoted in MT5
    lots: float
    have_lots: float
    want_lots: float
    stop: float          # stop-loss price for the resulting position (0 = flat)


@dataclass
class FxTicket:
    asof: str
    equity: float
    target_vol: float
    orders: List[FxOrder]
    targets: Dict[str, float]           # signed lots per pair
    stops: Dict[str, float]
    stop_distance_sigmas: float
    stop_risk_pct: float
    gross_usd: float
    warnings: List[str]

    def as_dict(self):
        d = asdict(self)
        d["orders"] = [asdict(o) for o in self.orders]
        return d


def to_currency_values(pair_px: pd.DataFrame) -> pd.DataFrame:
    """Pair quotes -> dollar value of each currency."""
    out = {}
    for pair, (ccy, usd_first) in PAIRS.items():
        if pair in pair_px:
            out[ccy] = 1.0 / pair_px[pair] if usd_first else pair_px[pair]
    return pd.DataFrame(out)


def reversal_weights(cv: pd.DataFrame, k: int = 3) -> pd.Series:
    """Signal at the LAST row: buy the 3 currencies that fell most against the
    basket, sell the 3 that rose most, inverse-volatility, gross = 1."""
    r = cv.pct_change().where(lambda x: x.abs() < 0.08)
    x = r.iloc[-1].dropna()
    w = pd.Series(0.0, index=cv.columns)
    if len(x) < 6:
        return w
    x = x - x.mean()
    o = x.sort_values().index
    w[o[:k]], w[o[-k:]] = 1.0, -1.0
    vol = r.iloc[-61:-1].std()
    w = (w / vol.where(vol > 0)).fillna(0.0)
    g = w.abs().sum()
    return w / g if g else w


def book_vol_1x(cv: pd.DataFrame, k: int = 3, lookback: int = 500) -> float:
    """Annualised volatility of the book at 1x gross, from its own history."""
    r = cv.pct_change().where(lambda x: x.abs() < 0.08)
    vol = r.rolling(60, min_periods=30).std()
    rets = []
    start = max(61, len(cv) - lookback)
    for t in range(start, len(cv) - 1):
        x = r.iloc[t].dropna()
        if len(x) < 6:
            continue
        x = x - x.mean()
        o = x.sort_values().index
        w = pd.Series(0.0, index=cv.columns)
        w[o[:k]], w[o[-k:]] = 1.0, -1.0
        w = (w / vol.iloc[t]).fillna(0.0)
        g = w.abs().sum()
        if g:
            rets.append(float(((w / g) * r.iloc[t + 1]).sum()))
    return float(np.std(rets) * np.sqrt(252)) if len(rets) > 30 else float("nan")


def lots_for(pair: str, usd_notional_in_ccy: float, price: float) -> float:
    """Signed lots of the PAIR that give the wanted dollar exposure to its
    currency. Positive = BUY the pair as quoted.

    XXXUSD: long XXX = buy the pair; one lot is 100,000 XXX = 100,000*price USD.
    USDXXX: long XXX = SELL the pair; one lot is 100,000 USD.
    """
    ccy, usd_first = PAIRS[pair]
    if usd_first:
        return -usd_notional_in_ccy / LOT
    return usd_notional_in_ccy / (LOT * price)


def build_fx_ticket(pair_hist: pd.DataFrame, quotes: Dict[str, float], *,
                    equity: float, initial_balance: float,
                    positions: Dict[str, float], asof: pd.Timestamp,
                    target_vol: float = 0.06, max_staleness_days: int = 5,
                    risk_budget: float = RISK_BUDGET) -> FxTicket:
    warnings: List[str] = []
    asof = pd.Timestamp(asof).normalize()
    gap = (asof - pair_hist.index[-1].normalize()).days
    if gap > max_staleness_days:
        raise ValueError(f"history ends {pair_hist.index[-1].date()}, {gap} days "
                         f"before {asof.date()} -- refresh data/daily first")
    missing = [p for p in PAIRS if not (quotes.get(p) and quotes[p] > 0)]
    if len(PAIRS) - len(missing) < 6:
        raise ValueError(f"only {len(PAIRS) - len(missing)} pairs quoted; the book "
                         "needs at least 6 to rank currencies against each other")
    if missing:
        warnings.append(f"no live quote for {', '.join(missing)}: excluded "
                        "today and left exactly as held")
    live = [p for p in PAIRS if p not in missing]
    hist = pair_hist[live][pair_hist.index.normalize() < asof]
    today = pd.DataFrame({p: [quotes[p]] for p in live}, index=[asof])
    px = pd.concat([hist, today])
    cv = to_currency_values(px)

    w = reversal_weights(cv)
    v1 = book_vol_1x(cv)
    if not np.isfinite(v1) or v1 <= 0:
        raise ValueError("not enough history to estimate the book's volatility")
    gross = target_vol / v1 * equity
    ccy_vol = cv.pct_change().iloc[-61:-1].std()      # daily, per currency

    targets, stops = {}, {}
    risk_unit = 0.0
    for p in live:
        ccy = PAIRS[p][0]
        notional = float(w.get(ccy, 0.0)) * gross
        lots = round(lots_for(p, notional, quotes[p]), 2)
        targets[p] = lots
        risk_unit += abs(notional) * float(ccy_vol.get(ccy, 0.0))
    # one multiple k of each position's daily volatility, chosen so the stops
    # together risk exactly the budget
    k = (risk_budget * initial_balance / risk_unit) if risk_unit > 0 else float("inf")
    for p in live:
        if targets[p] == 0:
            stops[p] = 0.0
            continue
        d = k * float(ccy_vol.get(PAIRS[p][0], 0.0))   # fractional move
        price = quotes[p]
        # long the PAIR -> stop below; short the PAIR -> stop above
        stops[p] = round(price * (1 - d) if targets[p] > 0 else price * (1 + d), 5)
    if k < 2.5:
        warnings.append(f"stops sit only {k:.1f} daily moves away and will be hit "
                        "often; lower --target-vol (risk cap: 3% of initial balance)")

    orders: List[FxOrder] = []
    for p in live:
        have = round(float(positions.get(p, 0.0)), 2)
        dq = round(targets[p] - have, 2)
        if abs(dq) >= 0.01:
            orders.append(FxOrder(p, "BUY" if dq > 0 else "SELL", abs(dq),
                                  have, targets[p], stops[p]))
    return FxTicket(asof=str(asof.date()), equity=equity, target_vol=target_vol,
                    orders=orders, targets=targets, stops=stops,
                    stop_distance_sigmas=round(k, 2),
                    stop_risk_pct=round(risk_budget * 100, 2),
                    gross_usd=round(gross, 0), warnings=warnings)


def format_fx_ticket(t: FxTicket) -> str:
    out = [f"FX ORDER TICKET  {t.asof}  equity ${t.equity:,.0f}  "
           f"vol target {t.target_vol*100:.1f}%  gross ${t.gross_usd:,.0f}",
           "Enter these MANUALLY in MetaTrader 5. This software sends nothing.",
           ""]
    if not t.orders:
        out.append("  no changes today -- hold current positions")
    for o in t.orders:
        stop = f"stop {o.stop}" if o.want_lots else "(closes the position)"
        out.append(f"  {o.side:4s} {o.lots:5.2f} lots {o.pair}   -> holding "
                   f"{o.want_lots:+.2f}   {stop}")
    out.append(f"\n  stops: {t.stop_distance_sigmas:.1f} daily moves away, "
               f"{t.stop_risk_pct:.1f}% of initial balance at risk in total")
    out.append("  move every remaining position's stop to the level above too")
    for w in t.warnings:
        out.append(f"  ! {w}")
    return "\n".join(out)
