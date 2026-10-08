import numpy as np
import pandas as pd
import pytest

from ares.combined import (MIN_MARKETS, CapitalTooSmall, check_viable,
                           combined_signal, reversal_weights, size_positions,
                           trend_weights)

IDX = pd.bdate_range("2015-01-01", periods=400)


def _panel(drifts):
    return pd.DataFrame(
        {k: 100 * np.cumprod(1 + np.full(len(IDX), d)) for k, d in drifts.items()},
        index=IDX)


def test_trend_leg_follows_direction():
    px = _panel({"UP": 0.001, "DOWN": -0.001})
    w = trend_weights(px, lookback=252)
    assert w["UP"] > 0 and w["DOWN"] < 0


def test_reversal_leg_buys_the_laggard_and_shorts_the_leader():
    px = _panel({f"M{i}": 0.0 for i in range(8)})
    px = px.copy()
    px.iloc[-1, 0] *= 0.97          # M0 dipped vs the basket
    px.iloc[-1, 1] *= 1.03          # M1 popped
    w = reversal_weights(px, lookback=1, top_k=2)
    assert w["M0"] > 0
    assert w["M1"] < 0


def test_reversal_leg_is_market_neutral_by_construction():
    """This is the grid's fatal flaw removed: equal longs and shorts means no
    directional bag can accumulate, and no hedge is needed."""
    px = _panel({f"M{i}": 0.0 for i in range(10)})
    px = px.copy()
    for j in range(10):
        px.iloc[-1, j] *= (1 + 0.01 * (j - 4.5) / 4.5)
    w = reversal_weights(px, lookback=1, top_k=3)
    assert abs(w.sum()) < 1e-9       # longs exactly offset shorts


def test_reversal_leg_stands_down_on_too_few_markets():
    px = _panel({"A": 0.0, "B": 0.001, "C": -0.001})
    w = reversal_weights(px, lookback=1, top_k=1)
    assert (w == 0).all()            # below MIN_MARKETS -> no position


def test_combined_signal_blends_both_legs():
    px = _panel({f"M{i}": 0.0005 * (i - 4) for i in range(9)})
    s = combined_signal(px, w_trend=0.5, top_k=2)
    assert s.weights and s.trend and s.reversal
    assert all(-1.0 - 1e-9 <= v <= 1.0 + 1e-9 for v in s.weights.values())


def test_capital_check_refuses_a_configuration_measured_to_lose():
    # 4 markets measured Sharpe -0.11; must raise, not warn
    with pytest.raises(CapitalTooSmall):
        check_viable(50_000.0, ["MES", "MNQ", "MGC", "MCL"])


def test_capital_check_refuses_undercapitalised_overnight_book():
    # 8 markets need ~$7.7k-12.7k of overnight margin; $5k cannot hold them
    with pytest.raises(CapitalTooSmall):
        check_viable(5_000.0, ["MES", "MNQ", "MYM", "M2K",
                               "MGC", "MCL", "M6E", "M6A"])


def test_capital_check_passes_a_viable_book():
    check_viable(25_000.0, ["MES", "MNQ", "MYM", "M2K",
                            "MGC", "MCL", "M6E", "M6A"])


def test_sizing_returns_whole_contracts_only():
    sig = combined_signal(_panel({f"M{i}": 0.0005 * (i - 4) for i in range(9)}),
                          top_k=2)
    prices = {f"M{i}": 100.0 for i in range(9)}
    vols = {f"M{i}": 0.15 for i in range(9)}
    mult = {f"M{i}": 5.0 for i in range(9)}
    pos = size_positions(sig, prices, capital=50_000.0, target_vol=0.03,
                         vols=vols, contract_multiplier=mult)
    assert all(isinstance(v, int) for v in pos.values())
    assert all(abs(v) <= 3 for v in pos.values())
