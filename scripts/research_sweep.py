#!/usr/bin/env python3
"""Research sweep: rank strategy configs by profit factor & consistency.

Goal = "profits beat losses, consistently" (profit factor > 1 with a high
share of positive months) — not a fixed dollar target. Runs a grid over
real data at $50, halts disabled so we measure raw edge over the full
sample. Overfitting warning: this searches many configs, so treat winners
as *candidates* to confirm out-of-sample, not as truth.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares import datasource
from ares.backtest import run_backtest
from ares.risk import RiskConfig
from ares.strategy import DonchianBreakoutStrategy, TrendPullbackStrategy
from ares.types import Costs

COSTS = Costs(taker_fee=0.0005, maker_fee=0.0002, slippage=0.0005)
NO_HALT = RiskConfig(max_total_drawdown=10.0, max_daily_drawdown=10.0)


def pct_positive_months(equity_curve):
    """Share of calendar months with a positive return."""
    if len(equity_curve) < 2:
        return 0.0, 0
    by_month = {}
    for ts, eq in equity_curve:
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        by_month[(d.year, d.month)] = eq          # last equity seen in month
    keys = sorted(by_month)
    rets = []
    for i in range(1, len(keys)):
        prev, cur = by_month[keys[i - 1]], by_month[keys[i]]
        if prev > 0:
            rets.append(cur / prev - 1.0)
    if not rets:
        return 0.0, 0
    pos = sum(1 for r in rets if r > 0)
    return pos / len(rets), len(rets)


def configs():
    for ch in (10, 20, 55):
        for short in (False, True):
            yield (f"breakout ch{ch}{'+short' if short else ''}",
                   DonchianBreakoutStrategy(channel=ch, allow_short=short))
    for short in (False, True):
        yield (f"pullback{'+short' if short else ''}",
               TrendPullbackStrategy(allow_short=short))


def main() -> int:
    rows = []
    for sym in ("BTCUSDT", "ETHUSDT"):
        for tf in ("1h", "4h", "1d"):
            path = f"data/{sym}_{tf}.csv"
            if not Path(path).exists():
                continue
            candles = datasource.load_csv(path)
            for name, strat in configs():
                r = run_backtest(candles, strat, symbol=sym, starting_capital=50.0,
                                 risk_config=NO_HALT, costs=COSTS)
                m = r.metrics
                posm, nmonths = pct_positive_months(r.equity_curve)
                rows.append((sym, tf, name, m["n_trades"], m["win_rate"],
                             m["profit_factor"], m["expectancy_r"],
                             m["total_return_pct"], m["max_drawdown_pct"], posm))

    # Keep configs with a meaningful sample, rank by profit factor
    rows = [r for r in rows if r[3] >= 20]
    rows.sort(key=lambda r: r[5], reverse=True)

    print(f"{'sym':<7}{'tf':<4}{'config':<18}{'trades':>7}{'win%':>6}"
          f"{'PF':>6}{'exp_R':>7}{'ret%':>8}{'maxDD%':>8}{'+mo%':>6}")
    print("-" * 77)
    for sym, tf, name, n, win, pf, exp, ret, dd, posm in rows[:25]:
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{sym:<7}{tf:<4}{name:<18}{n:>7}{win*100:>5.0f}%"
              f"{pf_s:>6}{exp:>+7.2f}{ret:>+8.1f}{dd:>8.1f}{posm*100:>5.0f}%")
    print("-" * 77)
    print("PF>1 = profits beat losses. +mo% = share of months in profit. "
          "Sweep = candidates, confirm out-of-sample before trusting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
