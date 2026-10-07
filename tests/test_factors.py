import numpy as np
import pandas as pd

from ares.factors import run_factor, signal_matrix

IDX = pd.bdate_range("2000-01-03", periods=900)


def _panel(trends):
    return pd.DataFrame(
        {k: 100 * np.cumprod(1 + np.full(len(IDX), d)) for k, d in trends.items()},
        index=IDX)


def test_tsmom_goes_long_an_uptrend_and_short_a_downtrend():
    px = _panel({"UP": 0.0008, "DOWN": -0.0008})
    s = signal_matrix(px, "tsmom").iloc[-1]
    assert s["UP"] > 0 and s["DOWN"] < 0


def test_xsmom_is_dollar_balanced_long_and_short():
    px = _panel({"A": 0.0010, "B": 0.0005, "C": 0.0, "D": -0.0005, "E": -0.0010,
                 "F": -0.0015})
    s = signal_matrix(px, "xsmom").iloc[-1]
    assert (s > 0).any() and (s < 0).any()
    assert abs(s.sum()) <= 1.0 + 1e-9          # roughly market-neutral by rank


def test_reversal_opposes_the_recent_move():
    px = _panel({"UP": 0.002})
    assert signal_matrix(px, "reversal").iloc[-1]["UP"] < 0


def test_factor_blend_runs_through_the_ledger_and_marks_honestly():
    px = _panel({"A": 0.0008, "B": -0.0006, "C": 0.0003})
    led = run_factor(px, ["tsmom", "xsmom"], capital=100_000.0, target_markets=3)
    assert len(led.curve) > 100
    # equity is derived from cash + marked positions, never assigned
    assert abs(led.equity() - (led.cash + sum(q * led.last_px[k]
                                              for k, q in led.pos.items() if q))) < 1e-6


def test_no_single_market_exceeds_the_notional_cap():
    px = _panel({"A": 0.0008, "B": -0.0006})
    led = run_factor(px, ["tsmom"], capital=100_000.0, target_markets=2,
                     max_notional_frac=0.25)
    for k, q in led.pos.items():
        assert abs(q) * led.last_px[k] <= 0.25 * 100_000.0 * 1.01
