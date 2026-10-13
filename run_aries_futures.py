#!/usr/bin/env python3
"""ARIES futures runner: the combined book (trend + cross-sectional reversal).

This is the one directional strategy in this repo that survived every check:
Sharpe +0.84 +/-0.16, t=5.37 over 57 years, out-of-sample half BETTER than
in-sample (0.92 vs 0.75), positive in all six decades, and built from two
effectively uncorrelated legs (+0.007) which is what halves the drawdown.

    # replay on history (works offline, proves the wiring):
    python run_aries_futures.py --replay --capital 25000

    # paper trade via Interactive Brokers (needs TWS/IB Gateway running):
    python run_aries_futures.py --paper --capital 25000           # observe only
    python run_aries_futures.py --paper --capital 25000 --submit  # send orders

    # live monitor (reads the state/dashboard.json that the above writes):
    python scripts/serve_dashboard.py     # http://127.0.0.1:8787/monitor/

READ BEFORE RUNNING WITH MONEY
  * Minimum viable capital is about $15,000. The book needs 6 markets and
    prefers 8; at 4 markets it measured Sharpe -0.11, i.e. a LOSS. Holding 8
    diversified micro futures overnight needs ~$7,750-12,700 of margin.
    ares.combined.check_viable() REFUSES undercapitalised configurations rather
    than warning, because silently running one turns a validated strategy into
    a losing one.
  * This book HOLDS OVERNIGHT. Almost every futures prop firm (Apex,
    Topstep, Tradeify, MyFundedFutures, Take Profit Trader, Bulenox, Lucid)
    force-liquidates before the daily close, so it cannot run there at all.
    Exactly one surveyed firm permits overnight and weekend holds on a funded
    account -- Phidias Premium -- and measuring the strategy against its
    actual rules gives an expected value near zero: its evaluation is a 2:1
    bet (make $6,000 before losing $3,000), which a Sharpe-0.41 book passes
    about a third of the time, the same as a coin weighted by that ratio
    alone. The gate needs roughly Sharpe 1.2 to pay. See docs/PROP_FIRMS.md
    and scripts/prop_firm_study.py. A broker has no such gate, which is why
    IBKR -- but note IBKR is a BROKER, so the capital is yours, not theirs.
  * Expect roughly 4%/yr at natural size on own capital. It is not fast, and
    the fast variants were tested and rejected (see docs/STRATEGY_RESEARCH.md).
  * Paper trading cannot validate the edge -- 57 years did that. What it
    verifies is fills, REAL commissions (cost sensitivity is severe here),
    contract rolls, and restart survival.
  * Nothing in here adapts or "learns" from live results. That is deliberate:
    every adaptive variant tested in this project made the measured result
    worse (see docs/STRATEGY_RESEARCH.md). The dashboard exists so a HUMAN can
    compare live behaviour against the replay and decide.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from ares.combined_backtest import backtest
from ares.combined import (MIN_VIABLE_CAPITAL, CapitalTooSmall, check_viable,
                           combined_signal, size_positions)
from ares.ibkr import (classify_port, import_ib, live_port_refusal,
                       ticker_price)
from ares.costs import cheapest
from ares.ledger import Ledger, summarise
from ares.ticket import build_ticket, format_ticket
from ares.monitor import Monitor
from ares.publish import Publisher

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


def run_replay(capital, target_vol, w_trend, top_k, monitor=True):
    px = load_history()
    check_viable(capital, list(px.columns))
    pub = Publisher()
    mon = (Monitor(strategy="combined", capital=capital, publisher=pub)
           if monitor else None)
    if mon:
        mon.mode = "replay"
        mon.connected = True
        mon.log("INFO", "SYSTEM", f"replay start, ${capital:,.0f}, "
                                  f"{len(px.columns)} markets",
                ts=int(px.index[253].value // 1_000_000) if len(px) > 253
                else None)
    log.info("replay: %d markets, %d days, %.1fyr", len(px.columns), len(px),
             (px.index[-1] - px.index[0]).days / 365.25)
    def _trade(ts, c, dq, price, fee):
        if mon:
            mon.record_trade(c, dq, price, fee, ts=ts)

    def _mark(i, ts, eq, prices, led):
        if mon and i % 21 == 0:
            mon.set_positions({c: {"qty": led.pos.get(c, 0.0),
                                   "price": prices.get(c, 0.0)}
                               for c in prices})
            mon.mark(eq, ts=ts)
            mon.flush()

    mult = {s_: m["mult"] for s_, m in UNIVERSE.items()}

    # Charge what a Phidias account actually pays: a fixed dollar commission
    # per contract plus half the spread, from the firm's published schedule
    # (ares/costs.py). The old flat 0.75bp-per-side rate understated the cost
    # of this book badly, because it holds its most contracts in the small
    # FX micros, where a fixed commission is several times dearer per dollar.
    def _cost(sym, units, price):
        return (units / mult[sym]) * cheapest(sym).side_usd()

    led = backtest(px, mult, capital=capital, target_vol=target_vol,
                   w_trend=w_trend, top_k=top_k, cost_fn=_cost,
                   on_trade=_trade, on_mark=_mark)
    ts = int(px.index[-1].value // 1_000_000)
    prices = {c: float(px[c].iloc[-1]) for c in px.columns
              if np.isfinite(px[c].iloc[-1])}
    s = summarise(led)
    if mon:
        # Final state must be exact. The in-loop snapshot runs every 21 bars
        # to keep the replay fast, which would otherwise leave the dashboard
        # showing month-old positions beside a final equity figure.
        mon.set_positions({c: {"qty": led.pos.get(c, 0.0),
                               "price": prices.get(c, 0.0)}
                           for c in prices})
        mon.mark(led.equity(), ts=ts)
        mon.log("INFO", "SYSTEM",
                f"replay done: {s.ann_return_pct:+.2f}%/yr, Sharpe "
                f"{s.sharpe:+.2f}, maxDD {s.max_drawdown_pct:.1f}%",
                ts=ts)
        mon.connected = False
        # A replay is history, not a live run, so it uploads once at the end
        # rather than on every one of the hundreds of in-loop flushes.
        mon.flush(publish=False)
        mon.flush(force_publish=True)
        log.info("  monitor state -> state/dashboard.json "
                 "(serve with: python scripts/serve_dashboard.py)")
        if pub.enabled:
            log.info("  published to %s", pub.url)
        else:
            log.info("  not published (%s); local only", pub.why_disabled())
    log.info("=" * 66)
    log.info("  combined book replay | $%.0f capital, %.0f%% vol target",
             capital, target_vol * 100)
    log.info("  %s", s)
    log.info("  fees paid $%.2f", s.fees_paid)
    log.info("=" * 66)
    return led


def run_paper(capital, target_vol, w_trend, top_k, strategy,
              interval=60, submit=False, allow_live=False):
    """Paper trade through IBKR, feeding the live dashboard every cycle.

    This runs as a LOOP, not a one-shot, because the point of the two-month
    paper phase is to watch the things a backtest cannot check: real fills,
    real commissions, contract rolls, and whether the process survives being
    left alone. Each cycle writes state/dashboard.json, so the dashboard shows
    live equity, live positions, every order, and the target-vs-actual gap.

    Orders are submitted only with --submit. Without it this is a read-only
    observer: it shows exactly what it WOULD do, which is the right default
    for the first few sessions.
    """
    IB, Future, MarketOrder, client = import_ib()
    px = load_history()
    check_viable(capital, list(px.columns))

    host = os.getenv("IB_HOST", "127.0.0.1")
    # TWS paper is 7497, IB Gateway paper is 4002. Both applications also have
    # a LIVE port (7496 and 4001), which is refused below.
    port = int(os.getenv("IB_PORT", "7497"))
    refusal = live_port_refusal(port, allow_live)
    if refusal:
        raise SystemExit(refusal)
    app, kind = classify_port(port)

    pub = Publisher()
    mon = Monitor(strategy=strategy, capital=capital, publisher=pub)
    mon.mode = kind
    if pub.enabled:
        log.info("publishing to %s", pub.url)
    else:
        log.info("not publishing (%s); the monitor is local only at "
                 "http://127.0.0.1:8787/monitor/", pub.why_disabled())
    mon.log("INFO", "SYSTEM",
            f"start {mon.mode}, ${capital:,.0f}, strategy={strategy}, "
            f"submit={'ON' if submit else 'OFF'}")
    mon.flush()

    ib = IB()
    ib.connect(host, port, clientId=int(os.getenv("IB_CLIENT_ID", "11")))
    mon.connected = True
    log.info("connected to %s %s:%d (%s account) via %s",
             app, host, port, kind, client)
    mon.log("INFO", "IBKR", f"connected to {app} {host}:{port}, {kind} account")
    if kind == "live":
        log.warning("THIS IS A LIVE ACCOUNT. Orders %s be submitted.",
                    "WILL" if submit else "will NOT")
        mon.log("WARN", "IBKR", "LIVE account"
                + (" with order submission ON" if submit else ", observing only"))

    contracts, tickers = {}, {}
    for sym, meta in UNIVERSE.items():
        found = ib.reqContractDetails(
            Future(symbol=sym, exchange=meta["exch"], currency="USD"))
        if not found:
            log.warning("no contract found for %s; skipping", sym)
            mon.log("WARN", sym, "no contract found; market skipped")
            continue
        # front month: nearest expiry. A roll is visible in the activity feed
        # as this value changing, which is one of the things paper trading is
        # meant to shake out.
        con = sorted((f.contract for f in found),
                     key=lambda x: x.lastTradeDateOrContractMonth)[0]
        contracts[sym] = con
        tickers[sym] = ib.reqMktData(con, "", False, False)
    log.info("resolved %d contracts", len(contracts))
    mon.log("INFO", "IBKR", f"resolved {len(contracts)} contracts: "
                            f"{', '.join(sorted(contracts))}")
    check_viable(capital, list(contracts))

    # Market data. A paper account usually has no real-time futures data
    # subscription, in which case every price comes back nan and the loop
    # would report "no live prices" forever with nothing saying why. Ask for
    # real-time, and if nothing arrives fall back to delayed and SAY SO --
    # delayed data is fine for a book that rebalances daily, but it must be a
    # stated choice, not a silent one.
    ib.sleep(4)
    if not any(ticker_price(t) for t in tickers.values()):
        log.warning("no real-time prices (the account most likely has no "
                    "futures market data subscription); using DELAYED data")
        mon.log("WARN", "IBKR", "no real-time data; switched to delayed")
        ib.reqMarketDataType(3)                 # 3 = delayed, 4 = delayed-frozen
        for sym, con in contracts.items():
            tickers[sym] = ib.reqMktData(con, "", False, False)
        ib.sleep(5)
        if not any(ticker_price(t) for t in tickers.values()):
            mon.log("ERROR", "IBKR", "no prices at all, real-time or delayed")
            mon.flush(force_publish=True)
            ib.disconnect()
            raise SystemExit(
                "No prices came back for any contract, real-time or delayed.\n"
                "Check in TWS/Gateway that the contracts appear in a watchlist "
                "and that API market data is enabled.")

    w = w_trend
    mult = {s: m["mult"] for s, m in UNIVERSE.items()}
    vol_w = px.pct_change().rolling(60, min_periods=30).std() * np.sqrt(252)
    vols = {c: float(vol_w[c].iloc[-1]) for c in px.columns
            if np.isfinite(vol_w[c].iloc[-1])}
    sig = combined_signal(px, w_trend=w, top_k=top_k)
    day = None
    try:
        while True:
            ib.sleep(2)                     # let the tickers populate
            prices = {}
            for sym, t in tickers.items():
                p = ticker_price(t)
                if p is not None:
                    prices[sym] = p
            if not prices:
                mon.log("WARN", "IBKR", "no live prices this cycle")
                mon.flush(); ib.sleep(interval); continue

            # Real account equity, not a simulated ledger. If the broker and
            # my arithmetic ever disagree, the broker is right.
            net_liq = capital
            for v in ib.accountSummary():
                if v.tag == "NetLiquidation":
                    net_liq = float(v.value)
            held = {p.contract.symbol: float(p.position) for p in ib.positions()
                    if p.contract.symbol in contracts}

            today = pd.Timestamp.utcnow().normalize()
            if day is not None and today != day:
                mon.roll_day()
            day = today

            want = size_positions(sig, prices, capital=net_liq,
                                  target_vol=target_vol, vols=vols,
                                  contract_multiplier=mult)
            for sym in sorted(prices):
                tgt = float(want.get(sym, 0))
                cur = held.get(sym, 0.0)
                dq = tgt - cur
                # Same no-trade band as the backtest. Matching it matters:
                # without it, whole-contract rounding churns the book and the
                # measured fee bill was ~5%/yr of capital.
                band = 0.34 * max(abs(tgt), abs(cur), 1e-9)
                act = abs(dq) >= 1 and (abs(dq) >= band or tgt == 0.0
                                        or np.sign(tgt) != np.sign(cur))
                if not act:
                    continue
                if not submit:
                    mon.log("INFO", sym, f"WOULD {'BUY' if dq > 0 else 'SELL'} "
                                         f"{abs(dq):g} (have {cur:g}, "
                                         f"want {tgt:g})")
                    continue
                order = MarketOrder("BUY" if dq > 0 else "SELL",
                                    int(round(abs(dq))))
                trade = ib.placeOrder(contracts[sym], order)
                ib.sleep(3)
                filled = sum(f.execution.shares for f in trade.fills)
                if filled:
                    avg = (sum(f.execution.shares * f.execution.price
                               for f in trade.fills) / filled)
                    comm = sum(getattr(f.commissionReport, "commission", 0.0) or 0.0
                               for f in trade.fills)
                    # Record the FILL, never the intent -- intent-based logs
                    # are how a paper run convinces you of trades that did not
                    # happen.
                    mon.record_trade(sym, filled * (1 if dq > 0 else -1),
                                     float(avg), float(comm),
                                     note=trade.orderStatus.status)
                else:
                    mon.log("WARN", sym, f"order {trade.orderStatus.status}, "
                                         f"no fill yet ({abs(dq):g} lots)")

            mon.set_positions({s: {"qty": held.get(s, 0.0),
                                   "price": prices.get(s, 0.0),
                                   "target": float(want.get(s, 0)),
                                   "mult": mult.get(s, 1.0)}
                               for s in sorted(prices)})
            mon.mark(net_liq)
            mon.flush()
            ib.sleep(interval)
    except KeyboardInterrupt:
        mon.log("INFO", "SYSTEM", "stopped by operator")
    except Exception as e:                           # noqa: BLE001
        # A crash must be visible ON THE DASHBOARD, not just in a terminal
        # that nobody is looking at.
        mon.last_error = f"{type(e).__name__}: {e}"
        mon.log("ERROR", "SYSTEM", mon.last_error)
        raise
    finally:
        mon.connected = False
        # force: the page must show "offline" promptly when the bot stops,
        # otherwise a dead bot looks like a quiet one.
        mon.flush(force_publish=True)
        ib.disconnect()


# Yahoo symbols for the SAME series the history files hold, so today's move
# is measured on the instrument the signal was built on.
YAHOO = {"SPX": "^GSPC", "NDX": "^IXIC", "DJI": "^DJI", "GOLD": "GC=F",
         "SILVER": "SI=F", "WTI": "CL=F", "EURUSD": "EURUSD=X",
         "AUDUSD": "AUDUSD=X"}


def fetch_quotes():
    """Latest price per tradeable symbol. A failure excludes that market for
    the day rather than inventing a price."""
    import json
    import urllib.parse
    import urllib.request
    out = {}
    for sym, meta in UNIVERSE.items():
        ysym = YAHOO.get(meta["data"])
        if not ysym:
            continue
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(ysym)}?range=1d&interval=5m")
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
            out[sym] = float(d["chart"]["result"][0]["meta"]["regularMarketPrice"])
        except Exception as e:                            # noqa: BLE001
            log.warning("no quote for %s (%s): %s", sym, ysym, e)
    return out


def run_ticket(equity, target_vol, w_trend, top_k,
               positions_path="state/positions.json"):
    """Print today's orders for MANUAL entry. Sends nothing, ever.

    Phidias permits only semi-automated software where the trader places and
    manages every order, so on a prop account this is the whole interface:
    run it about ten minutes before the 16:00 New York close, type the orders
    into Tradovate or Rithmic, then run --ticket-filled to record them.
    """
    import json
    px = load_history()
    pos_file = Path(positions_path)
    positions = json.loads(pos_file.read_text()) if pos_file.exists() else {}
    quotes = fetch_quotes()
    mult = {s_: m["mult"] for s_, m in UNIVERSE.items()}
    t = build_ticket(px, quotes, equity=equity, positions=positions,
                     mult=mult, asof=pd.Timestamp.now(tz="UTC").tz_localize(None),
                     target_vol=target_vol, w_trend=w_trend, top_k=top_k)
    print(format_ticket(t))
    Path("state").mkdir(exist_ok=True)
    Path("state/ticket.json").write_text(json.dumps(t.as_dict(), indent=2))
    mon = Monitor(strategy="reversal" if w_trend == 0 else "combined",
                  capital=equity, publisher=Publisher())
    mon.mode = "ticket"
    mon.connected = True
    for o in t.orders:
        mon.log("TICKET", o.symbol, f"{o.side} {o.qty} (have {o.have:+d}, "
                                    f"want {o.want:+d}) -- place manually")
    for w in t.warnings:
        mon.log("WARN", "TICKET", w)
    mon.set_positions({k: {"qty": float(positions.get(k, 0)), "target": float(v),
                           "price": float(quotes.get(k, 0) or 0),
                           "mult": mult.get(k, 1.0)}
                       for k, v in t.targets.items()})
    mon.mark(equity)
    mon.flush(force_publish=True)
    return t


def record_ticket_filled(positions_path="state/positions.json"):
    """After placing today's ticket by hand, adopt its targets as positions."""
    import json
    t = json.loads(Path("state/ticket.json").read_text())
    Path(positions_path).write_text(json.dumps(t["targets"], indent=2))
    print(f"recorded positions from the {t['asof']} ticket: {t['targets']}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", action="store_true")
    p.add_argument("--paper", action="store_true")
    p.add_argument("--ticket", action="store_true",
                   help="print today's orders for MANUAL entry (Phidias-"
                        "compliant: sends nothing)")
    p.add_argument("--ticket-filled", action="store_true",
                   help="record that today's ticket was placed by hand")
    p.add_argument("--equity", type=float, default=None,
                   help="current account balance, for --ticket")
    # Reversal-only is the default: the trend leg measured no edge in the
    # modern era (Sharpe +0.11-0.14, out-of-sample ~0) and every increment of
    # trend weight lowered the book's Sharpe. Under real per-contract costs
    # the two are about level (0.35 vs 0.34), so this is the simpler book at
    # no measured cost. See docs/SECOND_EDGE_SEARCH.md.
    p.add_argument("--strategy", choices=["combined", "reversal", "trend"],
                   default="reversal")
    p.add_argument("--capital", type=float, default=25_000.0)
    p.add_argument("--target-vol", type=float, default=0.03)
    p.add_argument("--w-trend", type=float, default=0.5)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--interval", type=int, default=60,
                   help="seconds between paper-mode cycles")
    p.add_argument("--submit", action="store_true",
                   help="actually send orders (paper mode). Without this the "
                        "runner only reports the orders it would send.")
    p.add_argument("--allow-live", action="store_true",
                   help="permit IB_PORT=7496, the LIVE trading port")
    a = p.parse_args()
    w = a.w_trend
    if a.strategy == "reversal":
        w = 0.0
    elif a.strategy == "trend":
        w = 1.0
    try:
        if a.ticket_filled:
            record_ticket_filled()
            return 0
        if a.ticket:
            if not a.equity:
                print("--ticket needs --equity (your account balance)",
                      file=sys.stderr)
                return 2
            run_ticket(a.equity, a.target_vol, w, a.top_k)
            return 0
        if a.replay:
            run_replay(a.capital, a.target_vol, w, a.top_k)
        elif a.paper:
            run_paper(a.capital, a.target_vol, w, a.top_k, a.strategy,
                      interval=a.interval, submit=a.submit,
                      allow_live=a.allow_live)
        else:
            print("Specify --replay, --paper or --ticket", file=sys.stderr)
            return 2
    except CapitalTooSmall as e:
        log.error("REFUSING TO RUN: %s", e)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
