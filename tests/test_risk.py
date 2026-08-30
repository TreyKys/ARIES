import pytest

from ares import risk as risk_mod
from ares.risk import AccountState, RiskConfig
from ares.types import Side, StrategyDecision


def _decision(stop):
    return StrategyDecision(side=Side.LONG, stop_price=stop,
                            take_profit_price=stop + 100, reason="test")


def _account(equity=1000.0, peak=None, day_start=None, day_pnl=0.0, losses=0):
    # peak/day_start default to equity so only the gate under test can trip
    peak = equity if peak is None else peak
    day_start = equity if day_start is None else day_start
    return AccountState(equity, peak, day_start, day_pnl, losses)


def test_sizing_is_risk_based():
    cfg = RiskConfig(risk_per_trade=0.015, max_position_leverage=5.0)
    rd = risk_mod.evaluate(_account(equity=1000.0), _decision(stop=95.0),
                           entry_price=100.0, cfg=cfg)
    assert rd.approved
    # risk = 1000 * 0.015 = 15; stop dist = 5 -> size 3.0; risk_amount 15
    assert rd.size == pytest.approx(3.0)
    assert rd.risk_amount == pytest.approx(15.0)


def test_leverage_cap_reduces_size():
    cfg = RiskConfig(risk_per_trade=0.015, max_position_leverage=5.0)
    rd = risk_mod.evaluate(_account(equity=50.0), _decision(stop=99.9),
                           entry_price=100.0, cfg=cfg)
    # uncapped size would be huge; notional capped at 50*5 = 250 -> size 2.5
    assert rd.approved
    assert rd.size == pytest.approx(2.5, abs=1e-6)


def test_rejects_below_min_notional():
    cfg = RiskConfig(min_notional=5.0)
    rd = risk_mod.evaluate(_account(equity=50.0), _decision(stop=50.0),
                           entry_price=100.0, cfg=cfg)
    assert not rd.approved and "minimum" in rd.reason.lower()


def test_total_drawdown_halt():
    cfg = RiskConfig(max_total_drawdown=0.10)
    rd = risk_mod.evaluate(_account(equity=89.0, peak=100.0),
                           _decision(stop=95.0), entry_price=100.0, cfg=cfg)
    assert not rd.approved and "drawdown" in rd.reason.lower()


def test_daily_loss_halt():
    cfg = RiskConfig(max_daily_drawdown=0.04)
    rd = risk_mod.evaluate(_account(equity=95.0, day_start=100.0, day_pnl=-5.0),
                           _decision(stop=90.0), entry_price=100.0, cfg=cfg)
    assert not rd.approved and "daily" in rd.reason.lower()


def test_adaptive_risk_after_losing_streak():
    cfg = RiskConfig(risk_per_trade=0.015, reduced_risk=0.005,
                     consec_loss_threshold=2)
    rd = risk_mod.evaluate(_account(equity=1000.0, losses=2),
                           _decision(stop=95.0), entry_price=100.0, cfg=cfg)
    # reduced risk 0.005 * 1000 = 5
    assert rd.approved and rd.risk_amount == pytest.approx(5.0)
