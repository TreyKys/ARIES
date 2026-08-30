#!/usr/bin/env python3
"""ARES engine entrypoint (deterministic core, PAPER mode).

Replay a CSV locally (works anywhere, proves the loop end to end):

    python run_engine.py --replay data/BTCUSDT_5m.csv --symbol BTC/USDT

Live on the VPS (polls the exchange; needs it reachable):

    python run_engine.py --live --symbols BTC/USDT,ETH/USDT --timeframe 5m

Reporting: if SUPABASE_URL/SUPABASE_KEY are set it writes the tables the
React dashboard reads; otherwise it logs to the console. LIVE-money mode
is intentionally NOT enabled here -- prove profitability first.
"""
import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from ares.feeds import ccxt_live_feed, replay_candles
from ares.live_engine import LiveEngine
from ares.reporting import ConsoleReporter, SupabaseReporter
from ares.strategy import TrendPullbackStrategy
from ares.types import Costs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ares")


def make_reporter():
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if url and key:
        try:
            log.info("Reporting to Supabase.")
            return SupabaseReporter(url, key)
        except Exception as e:  # noqa: BLE001
            log.warning("Supabase reporter unavailable (%s); using console.", e)
    log.info("No Supabase creds; reporting to console.")
    return ConsoleReporter()


def build_engine(symbol, reporter, capital):
    costs = Costs(taker_fee=0.0005, maker_fee=0.0002, slippage=0.0005)
    return LiveEngine(symbol, TrendPullbackStrategy(), starting_capital=capital,
                      costs=costs, reporter=reporter)


def run_replay(path, symbol, capital):
    reporter = make_reporter()
    engine = build_engine(symbol, reporter, capital)
    n = 0
    for candle in replay_candles(path):
        engine.step(candle)
        n += 1
    eq = engine.broker.equity
    wr = (engine.winning_trades / engine.total_trades * 100) if engine.total_trades else 0
    log.info("Replay done: %d candles | trades=%d win=%.1f%% final=$%.2f (start $%.2f)",
             n, engine.total_trades, wr, eq, capital)


async def run_live(symbols, timeframe, capital):
    reporter = make_reporter()
    engines = {s: build_engine(s, reporter, capital) for s in symbols}
    reporter.log("SYSTEM", f"ARES deterministic engine online (PAPER) on {', '.join(symbols)}", "INFO")

    async def on_candle(symbol, candle):
        engines[symbol].step(candle)

    await ccxt_live_feed(symbols, timeframe, on_candle)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--replay", default="")
    p.add_argument("--live", action="store_true")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--symbols", default="BTC/USDT,ETH/USDT")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--capital", type=float, default=50.0)
    args = p.parse_args()

    if args.replay:
        run_replay(args.replay, args.symbol, args.capital)
    elif args.live:
        asyncio.run(run_live([s.strip() for s in args.symbols.split(",")],
                             args.timeframe, args.capital))
    else:
        print("Specify --replay <csv> or --live", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
