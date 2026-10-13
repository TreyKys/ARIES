#!/usr/bin/env python3
"""WHEN is the daily reversal profit earned -- overnight, or in the day session?

This decides which prop firms the strategy can run at. Every futures prop firm
except Phidias Premium forces positions flat before the close (Apex, Topstep,
Tradeify, MyFundedFutures, Take Profit Trader, Lucid, Bulenox...). Those firms
are cheaper, more numerous, and frequently on sale. If the reversal edge is
earned in the DAY session, a flat-at-close version runs at all of them. If it
is earned overnight, Phidias is the only door.

It also answers an execution question the backtest has always assumed away:
the daily book computes its signal on the close and trades AT that close. Real
orders arrive later. Entering at the next morning's open is the natural
flat-overnight implementation, and it is also a direct test of whether the
edge survives a realistic delay.

Method: hourly Databento bars, 2011-2025. Each day the signal ranks the
eight markets on their close-to-close return, longs the three biggest
laggards and shorts the three biggest leaders, weights by inverse volatility.
The next day's holding return is split exactly into
    overnight = close(t)  -> open(t+1)     [what Phidias alone allows]
    day       = open(t+1) -> close(t+1)    [what every prop firm allows]
The two compound to the full close-to-close return, so nothing is lost or
double counted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EIGHT = ["ES", "NQ", "YM", "GC", "SI", "CL", "6E", "6A"]
RTH_OPEN, RTH_CLOSE = 14, 20     # UTC hours: 09:30-16:00 New York
TD = 252


def session_prices(sym: str) -> pd.DataFrame:
    d = pd.read_csv(f"data/futures_db_1h/{sym}.csv")
    s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    rth = s[(s.index.hour >= RTH_OPEN) & (s.index.hour <= RTH_CLOSE)]
    g = rth.groupby(rth.index.normalize())
    return pd.DataFrame({"open": g.first(), "close": g.last()})


def build():
    o, c = {}, {}
    for sym in EIGHT:
        sp = session_prices(sym)
        o[sym], c[sym] = sp["open"], sp["close"]
    O = pd.DataFrame(o).dropna()
    C = pd.DataFrame(c).reindex(O.index)
    return O, C


def weights(C: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
    """Signal known AT the close of day t, using only closes up to t."""
    r = C.pct_change()
    vol = r.rolling(60, min_periods=30).std()
    W = pd.DataFrame(0.0, index=C.index, columns=C.columns)
    for t in range(61, len(C)):
        x = r.iloc[t].dropna()
        if len(x) < 6:
            continue
        x = x - x.mean()
        order = x.sort_values().index
        v = vol.iloc[t]
        w = pd.Series(0.0, index=C.columns)
        w[order[:top_k]] = 1.0          # laggards: buy
        w[order[-top_k:]] = -1.0        # leaders: sell
        w = w / v.where(v > 0)          # equal risk per position
        w = w.fillna(0.0)
        gross = w.abs().sum()
        W.iloc[t] = w / gross if gross else 0.0
    return W


def sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(TD)) if x.std() else 0.0


def main() -> int:
    O, C = build()
    W = weights(C)
    # split the next day's return exactly into its two sessions
    overnight = (O / C.shift(1) - 1.0)          # close(t-1) -> open(t)
    day = (C / O - 1.0)                         # open(t)    -> close(t)
    full = (C / C.shift(1) - 1.0)
    Wl = W.shift(1)                              # positions set at prior close
    # A >15% move across one session boundary is a contract roll, not a
    # return; blank it rather than let the reversal leg feed on it.
    ok = (overnight.abs() < 0.15) & (day.abs() < 0.15)
    p_on = (Wl * overnight.where(ok)).sum(axis=1)
    p_dy = (Wl * day.where(ok)).sum(axis=1)
    p_fl = (Wl * full.where(ok)).sum(axis=1)
    keep = Wl.abs().sum(axis=1) > 0
    p_on, p_dy, p_fl = p_on[keep], p_dy[keep], p_fl[keep]
    yrs = (p_fl.index[-1] - p_fl.index[0]).days / 365.25

    print(f"\n{len(p_fl):,} trading days, {p_fl.index[0].date()} -> "
          f"{p_fl.index[-1].date()} ({yrs:.1f}yr), gross of costs\n")
    print(f"  {'holding window':32s} {'%/yr':>8} {'Sharpe':>8} {'t':>7}"
          f" {'share of edge':>14}")
    tot = p_fl.mean()
    for lab, x in (("close -> close (what the book does)", p_fl),
                   ("  overnight: close -> next open", p_on),
                   ("  day session: open -> close", p_dy)):
        t = x.mean() / x.std() * np.sqrt(len(x))
        print(f"  {lab:32s} {x.mean()*TD*100:+7.2f}% {sharpe(x):+8.2f}"
              f" {t:+7.2f} {x.mean()/tot*100:13.0f}%")

    print("\n  by three-year block (Sharpe, gross):")
    print(f"  {'period':>11} {'full':>7} {'overnight':>10} {'day':>7}")
    for y in range(2011, 2026, 3):
        m = (p_fl.index.year >= y) & (p_fl.index.year <= y + 2)
        if m.sum() > 200:
            print(f"  {y}-{y+2:>4} {sharpe(p_fl[m]):+7.2f} "
                  f"{sharpe(p_on[m]):+10.2f} {sharpe(p_dy[m]):+7.2f}")

    print("\n  per market, share of each market's reversal P&L:")
    print(f"  {'mkt':>5} {'overnight %/yr':>15} {'day %/yr':>10}")
    for m in C.columns:
        on = (Wl[m] * overnight[m].where(ok[m]))[keep]
        dy = (Wl[m] * day[m].where(ok[m]))[keep]
        print(f"  {m:>5} {on.mean()*TD*100:+14.3f}% {dy.mean()*TD*100:+9.3f}%")

    # turnover of the gross-normalised book, to price it later
    turn = (W - W.shift(1)).abs().sum(axis=1)[keep].mean()
    print(f"\n  average daily turnover of the book: {turn:.2f}x its gross")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
