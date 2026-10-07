#!/usr/bin/env python3
"""ARIES deployment runner: delta-neutral funding carry on OKX.

This is the strategy the project plan is built on, and the only one in this
repo that survived honest validation: long spot + short perp so price risk
cancels, collecting the perpetual funding payment.

    # replay the real funding history (works offline):
    python run_aries_carry.py --replay --pairs ETHUSDT,BTCUSDT --capital 50

    # paper on live OKX funding (the 1.5-month VPS run):
    python run_aries_carry.py --live --pairs ETHUSDT,BTCUSDT --capital 50

Read before deploying:
  * Validated on 6.7yr of real Binance funding history: ETH +10.2%/yr at 1.07%
    max drawdown unlevered, BTC +9.0% at 1.42%. Always-on beats every gating
    scheme tested -- a rate>0 gate returned +0.0%/yr with 36% drawdown because
    fees ate the entire carry.
  * The carry is DECAYING. Gross by year on ETH: 2021 +37.5%, 2022 +0.8%,
    2024 +13.0%, 2025 +4.9%, 2026 +1.9%. Expect 2-5%/yr in the current regime,
    not the 6.7-year average, and expect negative-funding stretches (~30% of
    intervals in 2026).
  * A paper run of weeks CANNOT validate an edge (the standard error of a
    Sharpe ratio depends on elapsed years, not bar count). What it DOES verify,
    and what it is for: that both legs fill, that the hedge stays matched, that
    basis tracking error is as small as assumed, and that the engine survives
    restarts. Treat its P&L as a plumbing check, not as evidence.
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ares import okx
from ares.carry_engine import CarryEngine, CarryEngineConfig
from ares.reporting import ConsoleReporter, SupabaseReporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("aries.carry")


def make_reporter():
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if url and key:
        try:
            return SupabaseReporter(url, key)
        except Exception as e:  # noqa: BLE001
            log.warning("Supabase unavailable (%s); console only.", e)
    return ConsoleReporter()


def load_history(pair: str):
    import csv
    path = Path("data/funding") / f"{pair}.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}; run scripts/fetch_funding_history.py {pair}")
    with path.open() as f:
        return [(int(r["calc_time"]), float(r["last_funding_rate"]))
                for r in csv.DictReader(f)]


def run_replay(pairs, capital, leverage):
    cfg = CarryEngineConfig(leverage=leverage)
    eng = CarryEngine(pairs, starting_capital=capital, cfg=cfg,
                      reporter=ConsoleReporter())
    logging.getLogger("ares.report").setLevel(logging.WARNING)
    merged = sorted((ts, p, r) for p in pairs for ts, r in load_history(p))
    for ts, p, r in merged:
        eng.on_funding(p, ts, r)
    yrs = (merged[-1][0] - merged[0][0]) / 86_400_000 / 365.25
    ann = ((eng.equity / capital) ** (1 / yrs) - 1) * 100 if yrs > 0 else 0.0
    log.info("=" * 64)
    log.info("  ARIES carry replay: %s  (%.1fyr, leverage %.1fx)",
             ", ".join(pairs), yrs, leverage)
    log.info("  $%.2f -> $%.2f  (%+.1f%%, %+.2f%%/yr)",
             capital, eng.equity, (eng.equity / capital - 1) * 100, ann)
    log.info("=" * 64)


def run_live(pairs, capital, leverage, poll_s):
    if not okx.reachable():
        raise SystemExit("OKX unreachable from this host; see DEPLOY.md")
    cfg = CarryEngineConfig(leverage=leverage)
    reporter = make_reporter()
    eng = CarryEngine(pairs, starting_capital=capital, cfg=cfg, reporter=reporter)
    reporter.log("SYSTEM", f"ARIES carry online (PAPER) on {', '.join(pairs)} via OKX", "INFO")
    seen = {}
    while True:
        try:
            for p in pairs:
                q = okx.fetch_carry_quote(p)
                # Only credit a funding event once per settlement window.
                if seen.get(p) != q.next_funding_ms:
                    eng.on_funding(p, int(time.time() * 1000), q.funding_rate)
                    seen[p] = q.next_funding_ms
                reporter.log("CARRY", f"{p} spot {q.spot:,.2f} perp {q.perp:,.2f} "
                             f"basis {q.basis_bps:+.2f}bp funding {q.funding_rate*1e4:+.3f}bp/8h "
                             f"({q.funding_rate*3*365*100:+.2f}%/yr)", "INFO")
            pnl = eng.equity - capital
            reporter.state(balance=round(eng.equity, 4), today_pnl_abs=round(pnl, 4),
                           today_pnl_pct=round(pnl / capital * 100, 3),
                           win_rate=0.0, is_connected=True)
        except Exception as e:  # noqa: BLE001
            log.warning("poll failed (%s); retrying", e)
        time.sleep(poll_s)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--replay", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--pairs", default="ETHUSDT,BTCUSDT")
    p.add_argument("--capital", type=float, default=50.0)
    p.add_argument("--leverage", type=float, default=2.0)
    p.add_argument("--poll", type=float, default=300.0)
    a = p.parse_args()
    pairs = [s.strip() for s in a.pairs.split(",")]
    if a.replay:
        run_replay(pairs, a.capital, a.leverage)
    elif a.live:
        run_live(pairs, a.capital, a.leverage, a.poll)
    else:
        print("Specify --replay or --live", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
