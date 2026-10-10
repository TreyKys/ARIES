"""Tests for the candidate-edge slate.

The one property that matters for a signal is that it cannot see its own
future. A look-ahead bug does not crash or look wrong -- it produces a
beautiful backtest, which is the single most expensive failure mode in this
repo's history. So every edge is checked against it mechanically rather than
by reading the code.
"""
import numpy as np
import pandas as pd
import pytest

from ares.edges import EDGES, MAX_LOOKBACK, _long_short


@pytest.fixture()
def panel():
    rng = np.random.default_rng(7)
    n = MAX_LOOKBACK + 400
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.DataFrame(
        {f"M{i}": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
         for i in range(8)}, index=idx)


@pytest.mark.parametrize("name", sorted(EDGES))
def test_signal_ignores_the_future(panel, name):
    """Changing bars AFTER the window must not change the signal.

    Each edge is handed a window and must use only what is inside it. This
    rewrites the tail of the full panel and re-reads the same window: a
    signal that peeks would move.
    """
    fn = EDGES[name]
    win = panel.iloc[:MAX_LOOKBACK]
    before = fn(win, 3)
    tampered = panel.copy()
    tampered.iloc[MAX_LOOKBACK:] *= 3.0          # violent, obvious future
    after = fn(tampered.iloc[:MAX_LOOKBACK], 3)
    pd.testing.assert_series_equal(before, after)


@pytest.mark.parametrize("name", sorted(EDGES))
def test_signal_is_bounded_and_complete(panel, name):
    w = EDGES[name](panel.iloc[:MAX_LOOKBACK], 3)
    assert list(w.index) == list(panel.columns)
    assert np.isfinite(w.to_numpy()).all()
    assert w.abs().max() <= 1.0 + 1e-12


@pytest.mark.parametrize("name", sorted(EDGES))
def test_signal_survives_a_short_window(panel, name):
    """Early in a backtest the window is short. Signals must return zeros
    rather than raising or inventing a position from too little history."""
    w = EDGES[name](panel.iloc[:30], 3)
    assert list(w.index) == list(panel.columns)
    assert np.isfinite(w.to_numpy()).all()


@pytest.mark.parametrize("name", sorted(EDGES))
def test_signal_tolerates_missing_markets(panel, name):
    p = panel.copy()
    p.iloc[:, 0] = np.nan                        # a market with no data at all
    p.iloc[-5:, 1] = np.nan                      # one that went dark recently
    w = EDGES[name](p.iloc[:MAX_LOOKBACK], 3)
    assert np.isfinite(w.to_numpy()).all()


# --- the cross-sectional helper --------------------------------------------

def test_long_short_is_balanced_and_picks_the_right_ends():
    s = pd.Series({"a": -3.0, "b": -1.0, "c": 0.0, "d": 1.0,
                   "e": 2.0, "f": 5.0, "g": 0.5, "h": -0.5})
    w = _long_short(s, 2, long_high=True)
    assert w.sum() == 0.0, "a cross-sectional bet must be balanced"
    assert w["f"] == 1.0 and w["e"] == 1.0        # highest two
    assert w["a"] == -1.0 and w["b"] == -1.0      # lowest two
    flipped = _long_short(s, 2, long_high=False)
    pd.testing.assert_series_equal(flipped, -w)


def test_long_short_refuses_a_thin_cross_section():
    """Demeaning against two surviving markets is noise, not a market factor."""
    assert (_long_short(pd.Series({"a": 1.0, "b": 2.0}), 2,
                        long_high=True) == 0).all()


def test_long_short_ignores_non_finite_scores():
    s = pd.Series({"a": 1.0, "b": np.inf, "c": -np.inf, "d": np.nan,
                   "e": 2.0, "f": 3.0, "g": -1.0, "h": -2.0, "i": 0.5})
    w = _long_short(s, 2, long_high=True)
    assert np.isfinite(w.to_numpy()).all()
    assert w["b"] == 0.0 and w["c"] == 0.0 and w["d"] == 0.0
