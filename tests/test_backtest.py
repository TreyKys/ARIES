from dataclasses import dataclass
from typing import Optional

from ares import datasource
from ares.backtest import run_backtest
from ares.strategy import Bars, TrendPullbackStrategy
from ares.types import Costs, RiskDecision, Side, StrategyDecision
from ares.risk import RiskConfig


@dataclass
class AlwaysLong:
    """Test double: enter LONG whenever flat. Isolates broker/backtest math."""
    warmup: int = 2

    def evaluate(self, bars: Bars) -> Optional[StrategyDecision]:
        c = float(bars.close[-1])
        return StrategyDecision(side=Side.LONG, stop_price=c * 0.99,
                                take_profit_price=c * 1.02, reason="always")


def _candles():
    return datasource.generate_candles(n=1500, seed=11, timeframe="5m")


def test_backtest_reports_all_metrics():
    result = run_backtest(_candles(), TrendPullbackStrategy(),
                          starting_capital=50.0)
    for key in ("n_trades", "win_rate", "expectancy_r", "profit_factor",
                "total_return_pct", "max_drawdown_pct", "total_fees"):
        assert key in result.metrics
    assert result.metrics["n_trades"] >= 0


def test_backtest_is_deterministic():
    c = _candles()
    r1 = run_backtest(c, TrendPullbackStrategy(), starting_capital=50.0)
    r2 = run_backtest(c, TrendPullbackStrategy(), starting_capital=50.0)
    assert r1.final_equity == r2.final_equity
    assert r1.metrics["n_trades"] == r2.metrics["n_trades"]


def test_equity_identity_holds():
    result = run_backtest(_candles(), AlwaysLong(), starting_capital=50.0,
                          risk_config=RiskConfig(min_notional=1.0))
    assert result.metrics["n_trades"] > 0            # the stub must actually trade
    pnl_sum = sum(t.pnl for t in result.trades)
    assert result.final_equity == __import__("pytest").approx(50.0 + pnl_sum, abs=1e-6)


def test_fees_are_charged_and_reduce_pnl():
    candles = _candles()
    no_cost = run_backtest(candles, AlwaysLong(), starting_capital=50.0,
                           risk_config=RiskConfig(min_notional=1.0),
                           costs=Costs(taker_fee=0.0, maker_fee=0.0, slippage=0.0))
    with_cost = run_backtest(candles, AlwaysLong(), starting_capital=50.0,
                             risk_config=RiskConfig(min_notional=1.0),
                             costs=Costs(taker_fee=0.001, maker_fee=0.001, slippage=0.001))
    assert with_cost.metrics["total_fees"] > 0.0
    # identical fills, but costs must make the costed run worse
    assert with_cost.final_equity < no_cost.final_equity


def test_no_lookahead_entry_uses_signal_close_not_future():
    """A position opened on candle i must not be closed on candle i."""
    candles = _candles()
    result = run_backtest(candles, AlwaysLong(), starting_capital=50.0,
                          risk_config=RiskConfig(min_notional=1.0))
    for t in result.trades:
        assert t.exit_ts > t.entry_ts
