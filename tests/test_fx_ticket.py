"""Tests for the manual FX ticket.

The ticket is typed into MT5 by hand exactly as printed, so its errors are
trades. The most dangerous one is a sign error on the USD-first pairs: being
long the yen means SELLING USDJPY, and getting that backwards puts on the
exact opposite book. These tests pin it from several directions.
"""
import numpy as np
import pandas as pd
import pytest

from ares.fx_ticket import (PAIRS, build_fx_ticket, format_fx_ticket,
                            lots_for, to_currency_values)

BASE = {"EURUSD": 1.17, "GBPUSD": 1.30, "AUDUSD": 0.66, "NZDUSD": 0.58,
        "USDCAD": 1.38, "USDCHF": 0.80, "USDJPY": 150.0}


@pytest.fixture()
def hist():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=700)
    return pd.DataFrame({p: v * np.exp(np.cumsum(rng.normal(0, 0.005, 700)))
                         for p, v in BASE.items()}, index=idx)


def quotes(hist, ccy_moves):
    """Live quotes in which each named CURRENCY moved by the given fraction
    against the dollar since the last close."""
    q = {}
    for p, (ccy, usd_first) in PAIRS.items():
        last = float(hist[p].iloc[-1])
        m = ccy_moves.get(ccy, 0.0)
        # a currency up x% means XXXUSD up x%, but USDXXX DOWN
        q[p] = last / (1 + m) if usd_first else last * (1 + m)
    return q


def test_long_a_usd_first_currency_means_selling_the_pair():
    assert lots_for("USDJPY", +100_000, 150.0) < 0     # long JPY -> SELL USDJPY
    assert lots_for("USDJPY", -100_000, 150.0) > 0     # short JPY -> BUY USDJPY
    assert lots_for("EURUSD", +100_000, 1.17) > 0      # long EUR -> BUY EURUSD
    assert lots_for("EURUSD", -100_000, 1.17) < 0


def test_lot_sizes_carry_the_right_dollar_exposure():
    # 1 lot of USDXXX is 100,000 USD; 1 lot of XXXUSD is 100,000 XXX
    assert lots_for("USDCAD", 100_000, 1.38) == pytest.approx(-1.0)
    assert lots_for("EURUSD", 117_000, 1.17) == pytest.approx(1.0)


def test_currency_values_invert_only_usd_first_pairs(hist):
    cv = to_currency_values(hist)
    assert cv["EUR"].iloc[-1] == pytest.approx(hist["EURUSD"].iloc[-1])
    assert cv["JPY"].iloc[-1] == pytest.approx(1 / hist["USDJPY"].iloc[-1])


def test_buys_the_fallen_currencies_and_sells_the_risen(hist):
    # yen and franc collapse, aussie and kiwi surge, against the basket
    q = quotes(hist, {"JPY": -0.02, "CHF": -0.015, "EUR": -0.01,
                      "AUD": +0.02, "NZD": +0.018, "GBP": +0.012})
    t = build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                        positions={}, asof=hist.index[-1] + pd.Timedelta(days=1))
    # long JPY/CHF must appear as SELLS of USDJPY/USDCHF
    assert t.targets["USDJPY"] < 0, "fallen yen must be bought, i.e. USDJPY sold"
    assert t.targets["USDCHF"] < 0
    assert t.targets["AUDUSD"] < 0, "surged aussie must be sold"
    assert t.targets["NZDUSD"] < 0


def test_stops_sit_on_the_losing_side_of_each_position(hist):
    q = quotes(hist, {"JPY": -0.02, "AUD": +0.02, "EUR": -0.01,
                      "NZD": +0.015, "CHF": -0.012, "GBP": +0.01})
    t = build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                        positions={}, asof=hist.index[-1] + pd.Timedelta(days=1))
    for p, lots in t.targets.items():
        if lots > 0:
            assert t.stops[p] < q[p], f"long {p}: stop must be below price"
        elif lots < 0:
            assert t.stops[p] > q[p], f"short {p}: stop must be above price"


def test_total_stop_risk_respects_the_budget(hist):
    q = quotes(hist, {"JPY": -0.02, "AUD": +0.02, "EUR": -0.01,
                      "NZD": +0.015, "CHF": -0.012, "GBP": +0.01})
    t = build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                        positions={}, asof=hist.index[-1] + pd.Timedelta(days=1))
    risk = 0.0
    for p, lots in t.targets.items():
        if not lots:
            continue
        ccy, usd_first = PAIRS[p]
        units = abs(lots) * 100_000
        move = abs(q[p] - t.stops[p])
        # dollar loss if the stop is hit
        risk += units * move / (q[p] if usd_first else 1.0)
    # lot rounding can nudge it; it must stay under FundedNext's 3% cap
    assert risk <= 0.03 * 100_000


def test_holding_the_target_produces_no_orders(hist):
    q = quotes(hist, {"JPY": -0.02, "AUD": +0.02})
    asof = hist.index[-1] + pd.Timedelta(days=1)
    t1 = build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                         positions={}, asof=asof)
    t2 = build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                         positions=t1.targets, asof=asof)
    assert t2.orders == []


def test_refuses_stale_history(hist):
    with pytest.raises(ValueError, match="refresh"):
        build_fx_ticket(hist, quotes(hist, {}), equity=100_000,
                        initial_balance=100_000, positions={},
                        asof=hist.index[-1] + pd.Timedelta(days=20))


def test_refuses_with_too_few_quotes(hist):
    q = quotes(hist, {})
    for p in ("USDJPY", "USDCHF"):
        q[p] = float("nan")
    with pytest.raises(ValueError, match="at least 6"):
        build_fx_ticket(hist, q, equity=100_000, initial_balance=100_000,
                        positions={}, asof=hist.index[-1] + pd.Timedelta(days=1))


def test_ticket_text_is_explicitly_manual(hist):
    t = build_fx_ticket(hist, quotes(hist, {"JPY": -0.02, "AUD": 0.02}),
                        equity=100_000, initial_balance=100_000, positions={},
                        asof=hist.index[-1] + pd.Timedelta(days=1))
    text = format_fx_ticket(t)
    assert "MANUALLY" in text and "sends nothing" in text
