#!/usr/bin/env python3
"""Run a backtest of the deterministic ARES strategy and print honest metrics.

Examples
--------
    # Synthetic data (works anywhere, no network) -- good for a smoke test:
    python scripts/run_backtest.py --source synthetic

    # Real Binance data (run on the VPS where the exchange is reachable):
    python scripts/run_backtest.py --source ccxt --symbol BTC/USDT --timeframe 5m --candles 1500

    # Your own CSV (headers: ts,open,high,low,close,volume):
    python scripts/run_backtest.py --source csv --csv data/btc_5m.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares import datasource
from ares.backtest import run_backtest
from ares.risk import RiskConfig
from ares.strategy import DonchianBreakoutStrategy, TrendPullbackStrategy
from ares.types import Costs


def main() -> int:
    p = argparse.ArgumentParser(description="ARES deterministic backtester")
    p.add_argument("--source", choices=["synthetic", "ccxt", "csv"], default="synthetic")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--candles", type=int, default=1500)
    p.add_argument("--csv", default="")
    p.add_argument("--capital", type=float, default=50.0)
    p.add_argument("--strategy", choices=["trend", "breakout"], default="trend")
    p.add_argument("--channel", type=int, default=20)
    p.add_argument("--allow-short", action="store_true")
    p.add_argument("--eval-edge", action="store_true",
                   help="disable drawdown/daily halts to measure raw strategy edge "
                        "over the whole sample (evaluation only, not a live config)")
    args = p.parse_args()

    if args.source == "synthetic":
        candles = datasource.generate_candles(n=args.candles, timeframe=args.timeframe)
        label = f"synthetic ({args.candles} x {args.timeframe})"
    elif args.source == "csv":
        if not args.csv:
            print("--csv PATH is required for --source csv", file=sys.stderr)
            return 2
        candles = datasource.load_csv(args.csv)
        label = f"{args.csv} ({len(candles)} candles)"
    else:  # ccxt
        try:
            candles = datasource.fetch_ohlcv(args.symbol, args.timeframe, args.candles)
        except Exception as e:  # noqa: BLE001
            print(f"Failed to fetch from exchange: {e}", file=sys.stderr)
            print("Tip: run this on the VPS, or use --source synthetic/csv.", file=sys.stderr)
            return 1
        label = f"{args.symbol} {args.timeframe} ({len(candles)} candles)"

    if args.strategy == "breakout":
        strategy = DonchianBreakoutStrategy(channel=args.channel, allow_short=args.allow_short)
    else:
        strategy = TrendPullbackStrategy(allow_short=args.allow_short)
    # Binance USDⓈ-M taker ~0.05%/side; model spread+slippage at 0.05%.
    costs = Costs(taker_fee=0.0005, maker_fee=0.0002, slippage=0.0005)
    rc = (RiskConfig(max_total_drawdown=10.0, max_daily_drawdown=10.0)
          if args.eval_edge else RiskConfig())
    result = run_backtest(candles, strategy, symbol=args.symbol,
                          starting_capital=args.capital,
                          risk_config=rc, costs=costs)

    m = result.metrics
    print("=" * 68)
    print(f"  ARES backtest  |  data: {label}")
    print(f"  strategy: {type(strategy).__name__} (short={'on' if args.allow_short else 'off'})"
          f"  |  capital: ${args.capital:.2f}")
    print("=" * 68)
    print(f"  Trades ............. {m['n_trades']}")
    print(f"  Win rate ........... {m['win_rate']:.1%}")
    print(f"  Expectancy ......... {m['expectancy_r']:+.3f} R / trade")
    print(f"  Profit factor ...... {m['profit_factor']:.2f}")
    print(f"  Avg win / loss ..... {m['avg_win_r']:+.2f}R / {m['avg_loss_r']:+.2f}R")
    print(f"  Total return ....... {m['total_return_pct']:+.1f}%")
    print(f"  Max drawdown ....... {m['max_drawdown_pct']:.1f}%")
    print(f"  Fees paid .......... ${m['total_fees']:.2f}")
    print(f"  Final equity ....... ${result.final_equity:.2f}")
    print("=" * 68)
    verdict = "POSITIVE expectancy" if m["expectancy_r"] > 0 else "NEGATIVE expectancy"
    print(f"  Verdict: {verdict} after costs. "
          f"{'Worth forward-testing.' if m['expectancy_r'] > 0 else 'Do NOT deploy as-is.'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
