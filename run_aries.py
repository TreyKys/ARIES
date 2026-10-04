#!/usr/bin/env python3
"""ARES multi-pair deployment runner (paper).

Runs the hedged-grid engine across several pairs, splits capital evenly,
and reports the combined portfolio. Replay validates anywhere; live polls a
reachable exchange on the VPS.

    # validate on real history:
    python run_aries.py --replay --pairs ETHUSDT,SOLUSDT,LINKUSDT --tf 15m --capital 100

    # live on the VPS (needs a reachable exchange):
    python run_aries.py --live --pairs ETHUSDT,SOLUSDT,LINKUSDT --tf 15m --capital 100
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
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


def build_engines(pairs, capital, atr_mult, max_inventory):
    per = capital / len(pairs)
    quiet = ConsoleReporter()
    logging.getLogger("ares.report").setLevel(logging.WARNING)  # engines quiet; runner reports portfolio
    return {p: HedgedGridEngine(p, capital=per, atr_mult=atr_mult,
                                max_inventory=max_inventory, reporter=quiet)
            for p in pairs}


def portfolio_equity(engines):
    return sum(e.capital + e.realized for e in engines.values())


def run_replay(pairs, tf, capital, atr_mult, max_inventory):
    engines = build_engines(pairs, capital, atr_mult, max_inventory)
    data = {p: datasource.load_csv(f"data/{p}_{tf}.csv") for p in pairs}
    # merge all candles by timestamp so the portfolio advances in real time
    merged = sorted(((c.ts, p, c) for p in pairs for c in data[p]), key=lambda x: x[0])
    peak = capital; max_dd = 0.0
    for ts, p, candle in merged:
        engines[p].step(candle)
        eq = portfolio_equity(engines)
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
    eq = portfolio_equity(engines)
    days = (merged[-1][0] - merged[0][0]) / 86_400_000
    ann = ((eq / capital) ** (365 / days) - 1) * 100 if days > 0 else 0
    hits = sum(e.round_trips for e in engines.values())
    log.info("=" * 60)
    log.info("  ARES portfolio replay: %s", ", ".join(pairs))
    log.info("  %d days | hits=%d | $%.2f -> $%.2f (%.1f%%, %.1f%%/yr) | maxDD %.2f%%",
             days, hits, capital, eq, (eq / capital - 1) * 100, ann, max_dd * 100)
    log.info("=" * 60)


async def run_live(pairs, tf, capital, atr_mult, max_inventory):
    import asyncio
    from ares.feeds import ccxt_live_feed
    engines = build_engines(pairs, capital, atr_mult, max_inventory)
    reporter = make_reporter()
    reporter.log("SYSTEM", f"ARES portfolio online (PAPER) on {', '.join(pairs)}", "INFO")
    symbols = [p.replace("USDT", "/USDT") for p in pairs]
    sym_to_pair = {s: p for s, p in zip(symbols, pairs)}

    async def on_candle(symbol, candle):
        engines[sym_to_pair[symbol]].step(candle)
        eq = portfolio_equity(engines)
        pnl = eq - capital
        reporter.state(balance=round(eq, 4), today_pnl_abs=round(pnl, 4),
                       today_pnl_pct=round(pnl / capital * 100, 3),
                       win_rate=0.0, is_connected=True)

    await ccxt_live_feed(symbols, tf, on_candle)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--pairs", default="ETHUSDT,SOLUSDT,LINKUSDT")
    p.add_argument("--tf", default="15m")
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--atr-mult", type=float, default=0.7)
    p.add_argument("--max-inventory", type=int, default=20)
    args = p.parse_args()
    pairs = [s.strip() for s in args.pairs.split(",")]

    if args.replay:
        run_replay(pairs, args.tf, args.capital, args.atr_mult, args.max_inventory)
    elif args.live:
        import asyncio
        asyncio.run(run_live(pairs, args.tf, args.capital, args.atr_mult, args.max_inventory))
    else:
        print("Specify --replay or --live", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
