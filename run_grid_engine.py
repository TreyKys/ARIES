#!/usr/bin/env python3
"""Run the hedged-grid engine (paper). The deployable 'our idea'.

Replay real history to validate (works anywhere):
    python run_grid_engine.py --replay data/ETHUSDT_15m.csv --symbol ETHUSDT

Live on the VPS (needs a reachable exchange + a real two-leg broker, TODO):
    python run_grid_engine.py --live --symbol ETHUSDT --timeframe 15m

Reporting: Supabase if SUPABASE_URL/KEY are set, else console.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ares import datasource
from ares.grid_engine import HedgedGridEngine
from ares.reporting import ConsoleReporter, SupabaseReporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("aries")


def make_reporter():
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if url and key:
        try:
            return SupabaseReporter(url, key)
        except Exception as e:  # noqa: BLE001
            log.warning("Supabase unavailable (%s); console.", e)
    return ConsoleReporter()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", default="")
    p.add_argument("--live", action="store_true")
    p.add_argument("--symbol", default="ETHUSDT")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--capital", type=float, default=50.0)
    p.add_argument("--atr-mult", type=float, default=0.5)
    p.add_argument("--max-inventory", type=int, default=20)
    args = p.parse_args()

    reporter = make_reporter()
    engine = HedgedGridEngine(args.symbol, capital=args.capital,
                              atr_mult=args.atr_mult, max_inventory=args.max_inventory,
                              reporter=reporter)
    if args.replay:
        logging.getLogger("ares.report").setLevel(logging.WARNING)  # quiet per-step spam
        candles = datasource.load_csv(args.replay)
        for c in candles:
            engine.step(c)
        eq = engine.capital + engine.realized
        log.info("Replay done: %s | %d candles | hits=%d | final=$%.2f (start $%.2f) | maxDD=%.2f%%",
                 args.symbol, len(candles), engine.round_trips, eq, args.capital, engine.max_dd * 100)
        return 0

    if args.live:
        import asyncio
        from ares.feeds import ccxt_live_feed

        async def on_candle(symbol, candle):
            engine.step(candle)

        reporter.log("SYSTEM", f"Hedged-grid engine online (PAPER) on {args.symbol}", "INFO")
        asyncio.run(ccxt_live_feed([args.symbol.replace("USDT", "/USDT")], args.timeframe, on_candle))
        return 0

    print("Specify --replay <csv> or --live", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
