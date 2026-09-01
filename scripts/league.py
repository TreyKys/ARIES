#!/usr/bin/env python3
"""ARES league: score every strategy x pair x timeframe out-of-sample.

Universe spans crypto AND forex. Each config is trained-window agnostic
(rules are fixed, not fit), run with asset-appropriate costs, and scored
on 2025 data held out from 2024/earlier. Results are ranked by
out-of-sample profit factor and saved to data/league_results.csv for
ongoing fine-tuning. Halts are disabled so we measure raw edge, not the
point where a circuit breaker truncated the sample.
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares import datasource
from ares.backtest import run_backtest
from ares.risk import RiskConfig
from ares.strategy import DonchianBreakoutStrategy, TrendPullbackStrategy
from ares.types import Costs

SPLIT = 1735689600000  # 2025-01-01

CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]
FOREX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GBPJPY", "USDCAD"]
CRYPTO_TF = ["1h", "4h", "1d"]
FOREX_TF = ["1h", "1d"]

# Asset-class cost + sizing models
CRYPTO_COSTS = Costs(taker_fee=0.0005, maker_fee=0.0002, slippage=0.0005)   # ~0.2% round trip
FOREX_COSTS = Costs(taker_fee=0.00003, maker_fee=0.00002, slippage=0.00003)  # ~1.2 pips majors
CRYPTO_RISK = RiskConfig(max_total_drawdown=10.0, max_daily_drawdown=10.0, qty_step=0.001, min_notional=5.0)
FOREX_RISK = RiskConfig(max_total_drawdown=10.0, max_daily_drawdown=10.0, qty_step=1.0, min_notional=1.0)


def strategies():
    return {
        "trend_long": lambda: TrendPullbackStrategy(allow_short=False),
        "trend_ls": lambda: TrendPullbackStrategy(allow_short=True),
        "bo20_fixed": lambda: DonchianBreakoutStrategy(channel=20, allow_short=True),
        "bo55_fixed": lambda: DonchianBreakoutStrategy(channel=55, allow_short=True),
        "bo20_trail": lambda: DonchianBreakoutStrategy(channel=20, allow_short=True, exit_mode="trail"),
        "bo55_trail": lambda: DonchianBreakoutStrategy(channel=55, allow_short=True, exit_mode="trail"),
        "bo55_trail_long": lambda: DonchianBreakoutStrategy(channel=55, allow_short=False, exit_mode="trail"),
    }


def pos_months(curve):
    if len(curve) < 2:
        return 0.0
    by = {}
    for ts, eq in curve:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        by[(d.year, d.month)] = eq
    ks = sorted(by)
    rets = [by[ks[i]] / by[ks[i - 1]] - 1 for i in range(1, len(ks)) if by[ks[i - 1]] > 0]
    return (sum(1 for r in rets if r > 0) / len(rets)) if rets else 0.0


def run_universe():
    rows = []
    universe = ([("crypto", s, tf) for s in CRYPTO for tf in CRYPTO_TF]
                + [("forex", s, tf) for s in FOREX for tf in FOREX_TF])
    for cls, sym, tf in universe:
        path = f"data/{sym}_{tf}.csv"
        if not Path(path).exists():
            continue
        candles = datasource.load_csv(path)
        oos = [c for c in candles if c.ts >= SPLIT]
        if len(oos) < 100:
            continue
        costs = CRYPTO_COSTS if cls == "crypto" else FOREX_COSTS
        risk = CRYPTO_RISK if cls == "crypto" else FOREX_RISK
        for name, make in strategies().items():
            r = run_backtest(oos, make(), symbol=sym, starting_capital=50.0,
                             risk_config=risk, costs=costs)
            m = r.metrics
            rows.append({
                "class": cls, "pair": sym, "tf": tf, "strategy": name,
                "trades": m["n_trades"], "win_pct": round(m["win_rate"] * 100, 1),
                "pf": m["profit_factor"], "exp_r": round(m["expectancy_r"], 3),
                "ret_pct": round(m["total_return_pct"], 1),
                "max_dd_pct": round(m["max_drawdown_pct"], 1),
                "pos_months_pct": round(pos_months(r.equity_curve) * 100, 0),
            })
    return rows


def fmt_pf(pf):
    return "inf" if pf == float("inf") else f"{pf:.2f}"


def leaderboard(rows, title, n=15):
    ranked = sorted([r for r in rows if r["trades"] >= 15 and r["pf"] != float("inf")],
                    key=lambda r: r["pf"], reverse=True)
    print(f"\n=== {title} (min 15 OOS trades, by profit factor) ===")
    print(f"{'pair':<9}{'tf':<4}{'strategy':<17}{'trades':>7}{'win%':>6}{'PF':>6}"
          f"{'exp_R':>7}{'ret%':>8}{'maxDD':>7}{'+mo%':>6}")
    for r in ranked[:n]:
        print(f"{r['pair']:<9}{r['tf']:<4}{r['strategy']:<17}{r['trades']:>7}"
              f"{r['win_pct']:>5.0f}%{fmt_pf(r['pf']):>6}{r['exp_r']:>+7.2f}"
              f"{r['ret_pct']:>+8.1f}{r['max_dd_pct']:>6.1f}%{r['pos_months_pct']:>5.0f}%")


def main() -> int:
    rows = run_universe()
    Path("data").mkdir(exist_ok=True)
    with open("data/league_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    winners = [r for r in rows if r["trades"] >= 15 and r["pf"] not in (float("inf"),)]
    profitable = [r for r in winners if r["pf"] > 1.0]
    print(f"Ran {len(rows)} backtests (OOS 2025). "
          f"{len(profitable)}/{len(winners)} configs with >=15 trades were profitable (PF>1).")
    leaderboard(rows, "OVERALL")
    leaderboard([r for r in rows if r["class"] == "crypto"], "CRYPTO")
    leaderboard([r for r in rows if r["class"] == "forex"], "FOREX")
    print("\nFull results -> data/league_results.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
