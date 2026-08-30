"""Backtester: run a strategy over history and measure it honestly.

Drives the same Strategy -> RiskManager -> PaperBroker path the live loop
uses, so a backtest is a faithful dry run. All metrics are computed after
fees and slippage. This is the tool that answers the only question that
matters before real money: does this actually have an edge?
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import risk as risk_mod
from .broker import PaperBroker
from .risk import AccountState, RiskConfig
from .strategy import Bars, Strategy
from .types import Candle, Costs, Trade

_MS_PER_DAY = 86_400_000


@dataclass
class BacktestResult:
    trades: List[Trade]
    equity_curve: List[Tuple[int, float]]
    metrics: dict
    final_equity: float
    starting_capital: float

    def summary(self) -> str:
        m = self.metrics
        return (
            f"trades={m['n_trades']}  win_rate={m['win_rate']:.1%}  "
            f"expectancy={m['expectancy_r']:+.3f}R  profit_factor={m['profit_factor']:.2f}  "
            f"return={m['total_return_pct']:+.1f}%  maxDD={m['max_drawdown_pct']:.1f}%  "
            f"fees=${m['total_fees']:.2f}"
        )


def bars_from_candles(candles: Sequence[Candle]) -> Bars:
    return Bars(
        ts=np.array([c.ts for c in candles], dtype=np.int64),
        open=np.array([c.open for c in candles], dtype=float),
        high=np.array([c.high for c in candles], dtype=float),
        low=np.array([c.low for c in candles], dtype=float),
        close=np.array([c.close for c in candles], dtype=float),
        volume=np.array([c.volume for c in candles], dtype=float),
    )


def compute_metrics(trades: List[Trade], equity_curve: List[Tuple[int, float]],
                    starting_capital: float, final_equity: float) -> dict:
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "win_rate": 0.0, "expectancy_r": 0.0,
            "profit_factor": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0,
            "total_return_pct": (final_equity / starting_capital - 1.0) * 100.0,
            "max_drawdown_pct": _max_drawdown_pct(equity_curve),
            "total_fees": 0.0,
        }
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    r_values = [t.r_multiple for t in trades]
    return {
        "n_trades": n,
        "win_rate": len(wins) / n,
        "expectancy_r": float(np.mean(r_values)),
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
        "avg_win_r": float(np.mean([t.r_multiple for t in wins])) if wins else 0.0,
        "avg_loss_r": float(np.mean([t.r_multiple for t in losses])) if losses else 0.0,
        "total_return_pct": (final_equity / starting_capital - 1.0) * 100.0,
        "max_drawdown_pct": _max_drawdown_pct(equity_curve),
        "total_fees": sum(t.fees for t in trades),
    }


def _max_drawdown_pct(equity_curve: List[Tuple[int, float]]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    max_dd = 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
    return max_dd * 100.0


def run_backtest(
    candles: Sequence[Candle],
    strategy: Strategy,
    *,
    symbol: str = "SYM",
    starting_capital: float = 50.0,
    risk_config: Optional[RiskConfig] = None,
    costs: Optional[Costs] = None,
) -> BacktestResult:
    risk_config = risk_config or RiskConfig()
    broker = PaperBroker(starting_capital, costs)

    all_bars = bars_from_candles(candles)
    n = len(candles)

    peak = starting_capital
    consecutive_losses = 0
    cur_day: Optional[int] = None
    day_start_equity = starting_capital
    equity_curve: List[Tuple[int, float]] = []

    for i in range(n):
        candle = candles[i]

        day = candle.ts // _MS_PER_DAY
        if day != cur_day:
            cur_day = day
            day_start_equity = broker.equity

        # 1. manage any open position against this candle
        trade = broker.process(candle)
        if trade is not None:
            consecutive_losses = 0 if trade.pnl > 0 else consecutive_losses + 1

        # 2. if flat, ask the strategy using data up to & including this candle
        if broker.flat and (i + 1) >= getattr(strategy, "warmup", 0):
            window = Bars(
                ts=all_bars.ts[: i + 1], open=all_bars.open[: i + 1],
                high=all_bars.high[: i + 1], low=all_bars.low[: i + 1],
                close=all_bars.close[: i + 1], volume=all_bars.volume[: i + 1],
            )
            decision = strategy.evaluate(window)
            if decision is not None:
                entry_ref = candle.close
                account = AccountState(
                    equity=broker.equity, peak_equity=peak,
                    day_start_equity=day_start_equity,
                    day_pnl=broker.equity - day_start_equity,
                    consecutive_losses=consecutive_losses,
                )
                rd = risk_mod.evaluate(account, decision, entry_ref, risk_config)
                if rd.approved:
                    broker.open(symbol, decision, rd.size, rd.risk_amount, entry_ref, candle.ts)

        # 3. mark to market & track peak
        mtm = broker.mark_to_market(candle.close)
        peak = max(peak, mtm)
        equity_curve.append((candle.ts, mtm))

    # close any dangling position at the final close
    if not broker.flat:
        broker.close_at(candles[-1].close, candles[-1].ts, "end_of_data")
        equity_curve[-1] = (candles[-1].ts, broker.equity)

    metrics = compute_metrics(broker.trades, equity_curve, starting_capital, broker.equity)
    return BacktestResult(
        trades=broker.trades, equity_curve=equity_curve, metrics=metrics,
        final_equity=broker.equity, starting_capital=starting_capital,
    )
