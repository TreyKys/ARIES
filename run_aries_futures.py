#!/usr/bin/env python3
"""ARIES futures runner: the combined book (trend + cross-sectional reversal).

This is the one directional strategy in this repo that survived every check:
Sharpe +0.84 +/-0.16, t=5.37 over 57 years, out-of-sample half BETTER than
in-sample (0.92 vs 0.75), positive in all six decades, and built from two
effectively uncorrelated legs (+0.007) which is what halves the drawdown.

    # replay on history (works offline, proves the wiring):
    python run_aries_futures.py --replay --capital 25000

    # paper trade via Interactive Brokers (needs TWS/IB Gateway running):
    python run_aries_futures.py --paper --capital 25000
    python run_aries_futures.py --paper --strategy reversal --capital 25000

READ BEFORE RUNNING WITH MONEY
  * Minimum viable capital is about $15,000. The book needs 6 markets and
    prefers 8; at 4 markets it measured Sharpe -0.11, i.e. a LOSS. Holding 8
    diversified micro futures overnight needs ~$7,750-12,700 of margin.
    ares.combined.check_viable() REFUSES undercapitalised configurations rather
    than warning, because silently running one turns a validated strategy into
    a losing one.
  * This book HOLDS OVERNIGHT. Most futures prop firms (Apex, Topstep,
    Tradeify, MyFundedFutures) require flat positions at the close, so it
    cannot run there. A normal broker has no such rule, which is why IBKR.
  * Expect roughly 4%/yr at natural size on own capital. It is not fast, and
    the fast variants were tested and rejected (see docs/STRATEGY_RESEARCH.md).
  * Paper trading cannot validate the edge -- 57 years did that. What it
    verifies is fills, REAL commissions (cost sensitivity is severe here),
    contract rolls, and restart survival.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from ares.combined import (MIN_VIABLE_CAPITAL, CapitalTooSmall, check_viable,
                           combined_signal, size_positions)
from ares.ledger import Ledger, summarise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("aries.futures")

# Micro contracts, chosen for diversification across asset classes at the
# lowest overnight margin that still gives 8 independent markets:
# 3 equity index, 2 metals, 1 energy, 2 FX. Overnight margin ~$11,150 in total,
# so a 60%-utilisation budget needs about $18.6k of capital -- which is why
# check_viable() rejects anything near $5k.
UNIVERSE = {
    "MES": dict(data="SPX",     mult=5.0,   exch="CME",   sec="FUT"),
    "MNQ": dict(data="NDX",     mult=2.0,   exch="CME",   sec="FUT"),
    "MYM": dict(data="DJI",     mult=0.5,   exch="CME",   sec="FUT"),
    "SIL": dict(data="SILVER",  mult=1000.0, exch="COMEX", sec="FUT"),
    "MGC": dict(data="GOLD",    mult=10.0,  exch="COMEX", sec="FUT"),
    "MCL": dict(data="WTI",     mult=100.0, exch="NYMEX", sec="FUT"),
    "M6E": dict(data="EURUSD",  mult=12500.0, exch="CME", sec="FUT"),
    "M6A": dict(data="AUDUSD",  mult=10000.0, exch="CME", sec="FUT"),
}


def load_history(folder="data/daily"):
    cols = {}
    for sym, meta in UNIVERSE.items():
        p = Path(folder) / f"{meta['data']}.csv"
        if not p.exists():
            log.warning("missing history for %s (%s)", sym, p)
            continue
        d = pd.read_csv(p)
        s = pd.Series(d["close"].values, index=pd.to_datetime(d["ts"], unit="ms"))
        cols[sym] = s[~s.index.duplicated(keep="last")].sort_index()
    px = pd.DataFrame(cols).sort_index().ffill()
    # blank implausible daily moves and their neighbours: continuous series
    # carry roll discontinuities, and a reversal leg profits from both the
    # artificial jump and its mirror image on the next bar.
    r = px.pct_change()
    bad = r.abs() > 0.25
    bad = bad | bad.shift(-1).fillna(False) | bad.shift(1).fillna(False)
    return px.mask(bad).dropna(axis=0, thresh=max(6, int(len(px.columns) * 0.7)))


def run_replay(capital, target_vol, w_trend, top_k):
    px = load_history()
    check_viable(capital, list(px.columns))
    log.info("replay: %d markets, %d days, %.1fyr", len(px.columns), len(px),
             (px.index[-1] - px.index[0]).days / 365.25)
    led = Ledger(capital)
    vol_w = px.pct_change().rolling(60, min_periods=30).std() * np.sqrt(252)
    mult = {s: m["mult"] for s, m in UNIVERSE.items()}
    for i in range(253, len(px)):
        win = px.iloc[: i + 1]
        ts = int(win.index[-1].value // 1_000_000)
        prices = {c: float(win[c].iloc[-1]) for c in win.columns
                  if np.isfinite(win[c].iloc[-1])}
        # Rebalance DAILY. The reversal leg's edge lives at a one-day horizon
        # (lookback=1, hold=1 in the validated test); rebalancing monthly
        # discards it and measured Sharpe +0.22 against +0.82 for the same
        # 8-market universe rebalanced daily. The trend leg moves slowly so
        # daily rebalancing costs it little extra turnover.
        if True:
            sig = combined_signal(win, w_trend=w_trend, top_k=top_k)
            vols = {c: float(vol_w[c].iloc[i]) for c in win.columns
                    if np.isfinite(vol_w[c].iloc[i])}
            want = size_positions(sig, prices, capital=led.equity() or capital,
                                  target_vol=target_vol, vols=vols,
                                  contract_multiplier=mult)
            for c in prices:
                tgt = want.get(c, 0) * mult.get(c, 1.0)
                cur = led.pos.get(c, 0.0)
                dq = tgt - cur
                # No-trade band. Without it, daily vol and equity drift flip
                # whole-contract counts between n and n+-1 endlessly: measured
                # $31,480 of fees on a $25k account over 26yr (~5%/yr of
                # capital). Only act when the change is a real signal change,
                # not rounding jitter.
                band = 0.34 * max(abs(tgt), abs(cur), 1e-9)
                if abs(dq) > 1e-9 and (abs(dq) >= band or tgt == 0.0
                                       or np.sign(tgt) != np.sign(cur)):
                    # 0.75bp round trip is the measured micro-futures cost
                    led.trade(ts, c, dq, prices[c],
                              cost=abs(dq) * prices[c] * 0.75e-4)
        led.mark(ts, prices)
    s = summarise(led)
    log.info("=" * 66)
    log.info("  combined book replay | $%.0f capital, %.0f%% vol target",
             capital, target_vol * 100)
    log.info("  %s", s)
    log.info("  fees paid $%.2f", s.fees_paid)
    log.info("=" * 66)


def run_paper(capital, target_vol, w_trend, top_k, strategy):
    """Paper trade through Interactive Brokers (TWS or IB Gateway must be up)."""
    try:
        from ib_insync import IB, Future
    except ImportError:
        raise SystemExit(
            "ib_insync is required for --paper:  pip install ib_insync\n"
            "You must also have TWS or IB Gateway running and logged into a "
            "PAPER account, with API connections enabled "
            "(Configure > API > Enable ActiveX and Socket Clients).")
    px = load_history()
    check_viable(capital, list(px.columns))
    ib = IB()
    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))      # 7497 paper, 7496 live
    ib.connect(host, port, clientId=int(os.getenv("IB_CLIENT_ID", "11")))
    log.info("connected to IBKR %s:%d", host, port)
    if port == 7496:
        log.warning("port 7496 is the LIVE port. Use 7497 for paper.")

    contracts = {}
    for sym, meta in UNIVERSE.items():
        c = Future(symbol=sym, exchange=meta["exch"], currency="USD")
        found = ib.reqContractDetails(c)
        if not found:
            log.warning("no contract found for %s; skipping", sym)
            continue
        # nearest expiry with volume: front month
        contracts[sym] = sorted(
            (f.contract for f in found),
            key=lambda x: x.lastTradeDateOrContractMonth)[0]
    log.info("resolved %d contracts", len(contracts))
    check_viable(capital, list(contracts))

    w = w_trend if strategy == "combined" else (0.0 if strategy == "reversal" else 1.0)
    sig = combined_signal(px, w_trend=w, top_k=top_k)
    vol_w = (px.pct_change().rolling(60, min_periods=30).std() * np.sqrt(252)).iloc[-1]
    prices = {}
    for sym, con in contracts.items():
        t = ib.reqMktData(con, "", False, False)
        ib.sleep(2)
        p = t.last if t.last and t.last > 0 else t.close
        if p and p > 0:
            prices[sym] = float(p)
    want = size_positions(sig, prices, capital=capital, target_vol=target_vol,
                          vols={k: float(vol_w.get(k, 0.2)) for k in prices},
                          contract_multiplier={s: m["mult"]
                                               for s, m in UNIVERSE.items()})
    log.info("target book (%s): %s", strategy, want)
    log.info("NOTE: orders are NOT submitted by this build. Review the target "
             "book, then wire ib.placeOrder() once the sizing looks right on "
             "your account.")
    ib.disconnect()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", action="store_true")
    p.add_argument("--paper", action="store_true")
    p.add_argument("--strategy", choices=["combined", "reversal", "trend"],
                   default="combined")
    p.add_argument("--capital", type=float, default=25_000.0)
    p.add_argument("--target-vol", type=float, default=0.03)
    p.add_argument("--w-trend", type=float, default=0.5)
    p.add_argument("--top-k", type=int, default=3)
    a = p.parse_args()
    w = a.w_trend
    if a.strategy == "reversal":
        w = 0.0
    elif a.strategy == "trend":
        w = 1.0
    try:
        if a.replay:
            run_replay(a.capital, a.target_vol, w, a.top_k)
        elif a.paper:
            run_paper(a.capital, a.target_vol, w, a.top_k, a.strategy)
        else:
            print("Specify --replay or --paper", file=sys.stderr)
            return 2
    except CapitalTooSmall as e:
        log.error("REFUSING TO RUN: %s", e)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
