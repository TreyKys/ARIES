import numpy as np
import pytest

from ares.ledger import Ledger, summarise


def test_the_identity_price_pnl_equals_position_times_price_change():
    """THE invariant that all three phantom bugs violated.

    With no trades and no carry between two marks, the change in equity must
    equal exactly sum(position * change in price). Nothing else can create
    profit.
    """
    led = Ledger(10_000.0)
    led.trade(0, "A", 10.0, 100.0)
    led.trade(0, "B", -5.0, 50.0)          # a short leg
    before = led.mark(0, {"A": 100.0, "B": 50.0})
    after = led.mark(1, {"A": 103.0, "B": 52.0})
    expected = 10.0 * (103.0 - 100.0) + (-5.0) * (52.0 - 50.0)
    assert np.isclose(after - before, expected)


def test_a_fully_hedged_book_earns_nothing_from_any_price_path():
    """Why the hedged grid could never have worked. Long and short the same
    instrument in equal size: no price path whatsoever produces P&L."""
    led = Ledger(10_000.0)
    led.trade(0, "X", 7.0, 100.0)
    led.trade(0, "X", -7.0, 100.0)         # net zero
    start = led.mark(0, {"X": 100.0})
    g = np.random.default_rng(1)
    p = 100.0
    for i in range(1, 500):
        p *= float(np.exp(g.normal(0, 0.02)))
        eq = led.mark(i, {"X": p})
        assert np.isclose(eq, start)       # identical, every single step


def test_equity_cannot_be_assigned_only_derived():
    # There is deliberately no setter for profit. Guards against a future
    # refactor reintroducing `realized += ...`-style accounting.
    led = Ledger(1_000.0)
    assert not hasattr(led, "realized")
    assert "equity" in dir(led) and callable(led.equity)


def test_carry_is_tracked_separately_from_price_pnl():
    led = Ledger(1_000.0)
    led.trade(0, "A", 1.0, 100.0)
    led.mark(0, {"A": 100.0})
    led.accrue(5.0)
    eq = led.mark(1, {"A": 100.0})         # price unchanged
    assert np.isclose(eq, 1_000.0 + 5.0)
    assert np.isclose(led.carry_received, 5.0)


def test_fees_reduce_equity_and_are_tracked():
    led = Ledger(1_000.0)
    led.trade(0, "A", 1.0, 100.0, cost=2.0)
    eq = led.mark(0, {"A": 100.0})
    assert np.isclose(eq, 998.0)
    assert np.isclose(led.fees_paid, 2.0)


def test_round_trip_at_the_same_price_loses_exactly_the_fees():
    led = Ledger(1_000.0)
    led.trade(0, "A", 5.0, 20.0, cost=1.0)
    led.trade(1, "A", -5.0, 20.0, cost=1.0)
    eq = led.mark(1, {"A": 20.0})
    assert np.isclose(eq, 998.0)


def test_negative_cost_rejected():
    led = Ledger(100.0)
    with pytest.raises(ValueError):
        led.trade(0, "A", 1.0, 10.0, cost=-1.0)


def test_sharpe_standard_error_shrinks_with_YEARS_not_bars():
    """The statistical law that invalidated a session of intraday testing.

    Same elapsed time, 24x more bars: the Sharpe standard error must barely
    move, because it depends on elapsed years, not sample count.
    """
    g = np.random.default_rng(4)

    def build(n, span_days):
        led = Ledger(1000.0)
        led.trade(0, "A", 1.0, 100.0)
        p, step = 100.0, span_days * 86_400_000 // n
        for i in range(n):
            p *= float(np.exp(g.normal(0.0002, 0.01)))
            led.mark(int(i * step), {"A": p})
        return summarise(led, periods_per_year=n // (span_days // 365) or 252)

    daily = build(252, 365)
    hourly = build(252 * 24, 365)
    # 24x the data over the same year buys no real certainty about the mean
    assert hourly.sharpe_stderr > 0.5 * daily.sharpe_stderr
