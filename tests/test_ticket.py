"""Tests for the manual order ticket.

On a Phidias account the trader must place every order by hand, so the ticket
IS the interface to the market. Wrong sides, wrong quantities, or a ticket
built on stale data would be traded exactly as printed.
"""
import numpy as np
import pandas as pd
import pytest

from ares.combined import CapitalTooSmall
from ares.ticket import append_quotes, build_ticket, format_ticket

SYMS = ["MES", "MNQ", "MYM", "MGC", "SIL", "MCL", "M6E", "M6A"]
MULT = {"MES": 5.0, "MNQ": 2.0, "MYM": 0.5, "MGC": 10.0, "SIL": 1000.0,
        "MCL": 100.0, "M6E": 12500.0, "M6A": 10000.0}
BASE = {"MES": 6800.0, "MNQ": 25000.0, "MYM": 46000.0, "MGC": 4100.0,
        "SIL": 60.0, "MCL": 65.0, "M6E": 1.17, "M6A": 0.66}


@pytest.fixture()
def hist():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2025-01-01", periods=300)
    return pd.DataFrame({s: BASE[s] * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
                         for s in SYMS}, index=idx)


def quotes_from(hist, moves):
    last = hist.iloc[-1]
    return {s: float(last[s]) * (1 + moves.get(s, 0.0)) for s in SYMS}


def test_buys_the_laggards_and_sells_the_leaders(hist):
    q = quotes_from(hist, {"MNQ": -0.03, "MES": -0.025, "MYM": -0.02,
                           "MGC": +0.03, "SIL": +0.035, "MCL": +0.04})
    t = build_ticket(hist, q, equity=100_000, positions={}, mult=MULT,
                     asof=hist.index[-1] + pd.Timedelta(days=1),
                     target_vol=0.08)
    sides = {o.symbol: o.side for o in t.orders}
    for s in ("MNQ", "MES", "MYM"):
        assert sides.get(s) in (None, "BUY"), f"{s} fell most; must not be sold"
    for s in ("MGC", "SIL", "MCL"):
        assert sides.get(s) in (None, "SELL"), f"{s} rose most; must not be bought"
    assert any(o.side == "BUY" for o in t.orders)
    assert any(o.side == "SELL" for o in t.orders)


def test_orders_are_the_difference_from_current_positions(hist):
    q = quotes_from(hist, {"MNQ": -0.03, "MCL": +0.04})
    asof = hist.index[-1] + pd.Timedelta(days=1)
    flat = build_ticket(hist, q, equity=100_000, positions={}, mult=MULT,
                        asof=asof, target_vol=0.08)
    # already holding exactly the target -> nothing to do
    held = build_ticket(hist, q, equity=100_000, positions=flat.targets,
                        mult=MULT, asof=asof, target_vol=0.08)
    assert held.orders == []
    for o in flat.orders:
        assert o.qty == abs(o.want - o.have) and o.qty > 0


def test_refuses_stale_history(hist):
    q = quotes_from(hist, {})
    with pytest.raises(ValueError, match="refresh"):
        build_ticket(hist, q, equity=100_000, positions={}, mult=MULT,
                     asof=hist.index[-1] + pd.Timedelta(days=30),
                     target_vol=0.08)


def test_missing_quote_excludes_market_and_never_trades_it(hist):
    q = quotes_from(hist, {"MNQ": -0.03})
    q["MCL"] = float("nan")
    t = build_ticket(hist, q, equity=100_000, positions={"MCL": 2}, mult=MULT,
                     asof=hist.index[-1] + pd.Timedelta(days=1),
                     target_vol=0.08)
    assert "MCL" in t.excluded
    assert all(o.symbol != "MCL" for o in t.orders), \
        "a market with no live price must be left alone, not flattened"
    assert any("MCL" in w for w in t.warnings)


def test_refuses_when_too_few_markets_are_quoted(hist):
    q = {s: float("nan") for s in SYMS}
    q["MES"] = float(hist["MES"].iloc[-1])
    with pytest.raises(CapitalTooSmall):
        build_ticket(hist, q, equity=100_000, positions={}, mult=MULT,
                     asof=hist.index[-1] + pd.Timedelta(days=1),
                     target_vol=0.08)


def test_append_quotes_replaces_rather_than_duplicates_today(hist):
    today = hist.index[-1]
    out = append_quotes(hist, quotes_from(hist, {}), today)
    assert out.index.is_unique
    assert len(out) == len(hist)


def test_ticket_text_says_manual_and_never_claims_execution(hist):
    q = quotes_from(hist, {"MNQ": -0.03, "MCL": +0.04})
    t = build_ticket(hist, q, equity=100_000, positions={}, mult=MULT,
                     asof=hist.index[-1] + pd.Timedelta(days=1),
                     target_vol=0.08)
    text = format_ticket(t)
    assert "MANUALLY" in text
    assert "must not send orders" in text
    assert "filled" not in text.lower() and "executed" not in text.lower()
