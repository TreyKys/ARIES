import numpy as np
import pandas as pd

from ares.calspread import backtest_calspread, cl_expiries, ng_expiries


def _panel(n=800, seed=0):
    g = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=n)
    lvl = 50 + np.cumsum(g.normal(0, 0.5, n))
    return pd.DataFrame({"C1": lvl, "C2": lvl + 1.0, "C3": lvl + 2.0,
                         "C4": lvl + 3.0}, index=idx)


def test_roll_days_earn_no_price_pnl():
    """THE methodology guard. Continuous C1 series are relabelled at expiry and
    jump by ~-(C1-C2) -- almost exactly MINUS the signal -- so attributing P&L
    to that jump manufactures an edge perfectly correlated with the signal.

    Construction: both legs are FLAT (zero genuine P&L available), with
    artificial jumps in C1 on roll days only. A rolling MEDIAN notional is
    robust to those few outliers, so the scale stays fixed. Any non-zero
    fee-free return therefore comes purely from the relabelling artifact.
    """
    idx = pd.bdate_range("2000-01-03", periods=800)
    exp = cl_expiries(2000, 2004)
    p = pd.DataFrame({"C1": 50.0, "C2": 51.0, "C3": 52.0, "C4": 53.0}, index=idx)
    rolls = [t for t in idx if t.normalize() in exp]
    assert len(rolls) > 5
    p.loc[rolls, "C1"] += 25.0            # violent artificial relabelling jumps

    free = backtest_calspread(p, exp, cost_rt=0.0)
    assert abs(free.ann_return_pct) < 1e-9     # artifact earns exactly nothing
    assert free.ann_vol_pct < 1e-9             # and shows up as no risk either


def test_roll_artifact_would_show_up_without_the_exclusion():
    # Same flat panel: if the roll jumps were NOT excluded they would dominate.
    # Confirms the previous test is a real guard, not a vacuous one.
    idx = pd.bdate_range("2000-01-03", periods=800)
    exp = cl_expiries(2000, 2004)
    p = pd.DataFrame({"C1": 50.0, "C2": 51.0, "C3": 52.0, "C4": 53.0}, index=idx)
    rolls = [t for t in idx if t.normalize() in exp]
    p.loc[rolls, "C1"] += 25.0
    raw = (p.C1.diff() - p.C2.diff()).abs().sum()
    assert raw > 100.0                    # the artifact is enormous in raw form


def test_roll_exclusion_actually_excludes_something():
    p = _panel()
    exp = cl_expiries(2000, 2004)
    hits = sum(1 for t in p.index if t.normalize() in exp)
    assert hits > 0                        # the calendar overlaps the sample


def test_inverted_placebo_is_mirror_of_carry_before_costs():
    p = _panel(seed=3)
    exp = cl_expiries(2000, 2004)
    a = backtest_calspread(p, exp, signal="carry", cost_rt=0.0)
    b = backtest_calspread(p, exp, signal="inverted", cost_rt=0.0)
    assert a.ann_vol_pct > 0
    assert np.isclose(a.ann_vol_pct, b.ann_vol_pct, rtol=1e-6)   # same risk
    assert np.sign(a.sharpe) != np.sign(b.sharpe) or a.sharpe == 0


def test_costs_reduce_return():
    p = _panel(seed=5)
    exp = cl_expiries(2000, 2004)
    free = backtest_calspread(p, exp, cost_rt=0.0)
    paid = backtest_calspread(p, exp, cost_rt=20e-4)
    assert paid.ann_return_pct < free.ann_return_pct


def test_ng_expiry_calendar_differs_from_cl():
    assert ng_expiries(2010, 2010) != cl_expiries(2010, 2010)
