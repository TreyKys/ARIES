"""Tests for the dashboard monitor.

The monitor is read by a browser polling a file that a trading loop is writing
at the same time, so the two things that matter are (a) a reader never sees a
half-written file and (b) the unbounded lists stay bounded over a long run.
Both are invariants, not opinions, so they are tested rather than eyeballed.
"""
import json
import os

import pytest

from ares.monitor import MAX_ACTIVITY, MAX_CURVE, MAX_TRADES, Monitor


@pytest.fixture()
def mon(tmp_path):
    return Monitor(path=str(tmp_path / "state" / "dashboard.json"),
                   strategy="combined", capital=25_000.0)


def test_flush_writes_valid_json_and_no_temp_files(mon):
    mon.mark(25_100.0)
    mon.flush()
    d = json.loads(mon.path.read_text())
    assert d["equity"] == 25_100.0
    assert d["capital"] == 25_000.0
    # The atomic write must not leave .tmp droppings behind; the dashboard
    # directory is also the live state directory.
    assert [f for f in os.listdir(mon.path.parent) if f.endswith(".tmp")] == []


def test_flush_is_atomic_replace(mon):
    """Every flush must land as a complete file, never a truncated one."""
    mon.mark(25_000.0)
    mon.flush()
    first = mon.path.read_text()
    inode = mon.path.stat().st_ino
    mon.mark(30_000.0)
    mon.flush()
    second = mon.path.read_text()
    assert first != second
    # os.replace swaps a new file in, so the inode changes; an in-place
    # truncate+write (which a reader could catch mid-way) would keep it.
    assert mon.path.stat().st_ino != inode
    json.loads(second)


def test_trade_sides_and_activity_mirror(mon):
    mon.record_trade("MES", 2.0, 5100.25, cost=1.5)
    mon.record_trade("MGC", -1.0, 2400.0, cost=0.8)
    assert [t.side for t in mon.trades] == ["BUY", "SELL"]
    assert mon.trades[1].qty == 1.0          # magnitude, sign lives in side
    # every trade also shows up in the activity feed
    assert [a.level for a in mon.activity] == ["TRADE", "TRADE"]
    assert "MGC" in mon.activity[1].source


def test_pnl_and_drawdown(mon):
    for e in (25_000.0, 30_000.0, 27_000.0):
        mon.mark(e)
    s = mon.snapshot()
    assert s["pnl_abs"] == 2_000.0
    assert s["pnl_pct"] == pytest.approx(8.0, abs=1e-6)
    assert s["day_pnl_abs"] == 2_000.0
    # drawdown is measured from the peak of the curve, not from capital
    assert s["drawdown_pct"] == pytest.approx(10.0, abs=0.01)


def test_drawdown_is_zero_at_a_new_high(mon):
    mon.mark(25_000.0)
    mon.mark(40_000.0)
    assert mon.snapshot()["drawdown_pct"] == 0.0


def test_exposure_nets_longs_against_shorts(mon):
    mon.set_positions({
        "MES": {"qty": 2.0, "price": 5_000.0},     # +10,000
        "MGC": {"qty": -3.0, "price": 2_000.0},    # -6,000
        "MCL": {"qty": 0.0, "price": 70.0},        # flat
    })
    s = mon.snapshot()
    assert s["gross_exposure"] == 16_000.0
    assert s["net_exposure"] == 4_000.0
    assert s["n_positions"] == 2                   # flat legs do not count


def test_lists_stay_bounded(mon):
    for i in range(MAX_TRADES + 50):
        mon.record_trade("MES", 1.0, 5_000.0 + i)
    for i in range(MAX_CURVE + 50):
        mon.mark(25_000.0 + i)
    assert len(mon.trades) == MAX_TRADES
    assert len(mon.activity) == MAX_ACTIVITY
    assert len(mon.curve) == MAX_CURVE
    # the trimming must drop the OLDEST rows, keeping the most recent
    assert mon.trades[-1].price == 5_000.0 + MAX_TRADES + 49


def test_trades_and_activity_are_newest_first_in_snapshot(mon):
    mon.record_trade("MES", 1.0, 5_000.0)
    mon.record_trade("MNQ", 1.0, 18_000.0)
    s = mon.snapshot()
    assert s["trades"][0]["symbol"] == "MNQ"
    assert s["activity"][0]["source"] == "MNQ"


def test_snapshot_survives_zero_capital(tmp_path):
    """A monitor started before capital is known must not divide by zero."""
    m = Monitor(path=str(tmp_path / "dashboard.json"), capital=0.0)
    m.equity = 0.0
    s = m.snapshot()
    assert s["pnl_pct"] == 0.0
    assert s["drawdown_pct"] == 0.0


def test_log_levels_are_preserved(mon):
    mon.log("WARN", "ibkr", "reconnecting")
    mon.log("ERROR", "ibkr", "order rejected")
    s = mon.snapshot()
    assert [a["level"] for a in s["activity"]] == ["ERROR", "WARN"]
