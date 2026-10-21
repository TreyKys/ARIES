#!/usr/bin/env python3
"""ARIES FX: the FX-majors reversal book, as a MANUAL daily ticket for MT5.

Built for FundedNext Stellar 2-Step (swap-free): on accounts of $50,000 and
above FundedNext does not permit EAs, so this never trades. Run it once a day
at the same time, type the orders into MetaTrader 5, then record them:

    python run_aries_fx.py --equity 100000            # print today's ticket
    python run_aries_fx.py --filled                   # after placing it

Why this book: the seven FX majors, ranked as currencies against each other,
carry the most consistent edge measured in this project (gross Sharpe +0.49,
positive in every four-year block since 2004), and a swap-free account removes
the overnight swap that otherwise decides whether a CFD prop account pays.
See docs/FX_FUNDEDNEXT.md for what is verified and what is not.
"""
import argparse
import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ares.fx_ticket import PAIRS, build_fx_ticket, format_fx_ticket  # noqa: E402
from ares.monitor import Monitor                                      # noqa: E402
from ares.publish import Publisher                                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("aries.fx")

YAHOO = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X",
         "NZDUSD": "NZDUSD=X", "USDCAD": "CAD=X", "USDCHF": "CHF=X",
         "USDJPY": "JPY=X"}
POSITIONS = Path("state/fx_positions.json")
TICKET = Path("state/fx_ticket.json")


def load_history(folder="data/daily") -> pd.DataFrame:
    cols = {}
    for p in PAIRS:
        d = pd.read_csv(f"{folder}/{p}.csv")
        # Yahoo stamps some FX days at 23:00 UTC and others at 00:00 UTC;
        # shifting two hours puts both on the right date.
        idx = (pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms"))
               + pd.Timedelta(hours=2)).normalize()
        s = pd.Series(d["close"].values, index=idx)
        cols[p] = s[~s.index.duplicated(keep="last")].sort_index()
    df = pd.DataFrame(cols).sort_index()
    return df[df.index.dayofweek < 5].dropna(thresh=6).ffill()


def fetch_quotes() -> dict:
    out = {}
    for p, y in YAHOO.items():
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(y)}?range=1d&interval=5m")
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
            out[p] = float(d["chart"]["result"][0]["meta"]["regularMarketPrice"])
        except Exception as e:                            # noqa: BLE001
            log.warning("no quote for %s: %s", p, e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity", type=float, help="current account equity")
    ap.add_argument("--initial", type=float, default=100_000.0,
                    help="initial balance the firm's limits are measured on")
    ap.add_argument("--phase", choices=["challenge", "funded"], default="challenge",
                    help="challenge: stops protect the 5%% daily limit, 8%% vol; "
                         "funded: stops held inside the 3%% open-risk cap, 6%% vol")
    ap.add_argument("--target-vol", type=float, default=None,
                    help="override the phase's default annual volatility")
    ap.add_argument("--filled", action="store_true",
                    help="record that today's ticket was placed")
    a = ap.parse_args()

    if a.filled:
        t = json.loads(TICKET.read_text())
        POSITIONS.parent.mkdir(exist_ok=True)
        POSITIONS.write_text(json.dumps(t["targets"], indent=2))
        print(f"recorded positions from the {t['asof']} ticket")
        return 0
    if not a.equity:
        print("--equity is required (your current account equity)", file=sys.stderr)
        return 2

    # The two phases bind on different rules. In the challenge there is no
    # open-risk cap; the limit that matters is the 5% daily loss, so stops are
    # sized to keep even an all-stops-hit day under it, and the book runs at
    # the 8% the simulation found best. Funded accounts cap open risk at 3%
    # (a second breach cuts it to 1% for good), so stops must fit inside 2.5%,
    # and a lower vol keeps them far enough away not to be hit routinely.
    # Measured: funded at 4.5% vol puts stops 3.9 daily moves away but halves
    # expected payouts (EV +$537 vs +$1,026 at 0.3bp); 6% keeps them ~3 moves
    # away, still inside the cap. 8% would put them ~2 moves away.
    budget, vol = (0.045, 0.08) if a.phase == "challenge" else (0.025, 0.06)
    vol = a.target_vol or vol
    positions = json.loads(POSITIONS.read_text()) if POSITIONS.exists() else {}
    t = build_fx_ticket(load_history(), fetch_quotes(), equity=a.equity,
                        initial_balance=a.initial, positions=positions,
                        asof=pd.Timestamp.now(tz="UTC").tz_localize(None),
                        target_vol=vol, risk_budget=budget)
    print(format_fx_ticket(t))
    TICKET.parent.mkdir(exist_ok=True)
    TICKET.write_text(json.dumps(t.as_dict(), indent=2))

    mon = Monitor(strategy="fx-reversal", capital=a.initial, publisher=Publisher())
    mon.mode = "ticket"
    mon.connected = True
    for o in t.orders:
        mon.log("TICKET", o.pair, f"{o.side} {o.lots:.2f} lots -> {o.want_lots:+.2f}"
                                  f", stop {o.stop} -- place manually")
    for w in t.warnings:
        mon.log("WARN", "TICKET", w)
    mon.set_positions({p: {"qty": float(positions.get(p, 0.0)),
                           "target": float(v), "price": 0.0}
                       for p, v in t.targets.items()})
    mon.mark(a.equity)
    mon.flush(force_publish=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
