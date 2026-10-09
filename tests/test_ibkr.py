"""Tests for the two IBKR decisions that cannot be checked once connected:
which port is live, and what counts as a usable price.
"""
import pytest

from ares.ibkr import classify_port, live_port_refusal, ticker_price


class T:
    """Stand-in for an ib_insync/ib_async Ticker."""
    def __init__(self, **kw):
        self.last = kw.get("last", float("nan"))
        self.bid = kw.get("bid", float("nan"))
        self.ask = kw.get("ask", float("nan"))
        self.close = kw.get("close", float("nan"))
        self._mp = kw.get("mp")

    def marketPrice(self):
        if self._mp == "raise":
            raise RuntimeError("not available")
        return self._mp if self._mp is not None else float("nan")


# --- ports -----------------------------------------------------------------

@pytest.mark.parametrize("port,app,kind", [
    (7496, "TWS", "live"),
    (7497, "TWS", "paper"),
    (4001, "IB Gateway", "live"),
    (4002, "IB Gateway", "paper"),
])
def test_known_ports(port, app, kind):
    assert classify_port(port) == (app, kind)


@pytest.mark.parametrize("port", [7496, 4001])
def test_both_live_ports_are_refused(port):
    """4001 is IB Gateway's live port and was previously waved through."""
    msg = live_port_refusal(port, allow_live=False)
    assert msg and "LIVE" in msg
    assert "--allow-live" in msg


@pytest.mark.parametrize("port", [7497, 4002])
def test_paper_ports_are_allowed(port):
    assert live_port_refusal(port, allow_live=False) is None


def test_unknown_port_is_refused_rather_than_guessed():
    msg = live_port_refusal(4321, allow_live=False)
    assert msg and "cannot tell" in msg


@pytest.mark.parametrize("port", [7496, 4001, 4321])
def test_allow_live_overrides_every_refusal(port):
    assert live_port_refusal(port, allow_live=True) is None


# --- prices ----------------------------------------------------------------

def test_prefers_the_last_trade():
    assert ticker_price(T(last=5100.25, bid=5100.0, ask=5101.0,
                          close=5000.0)) == 5100.25


def test_falls_back_to_the_quote_midpoint():
    assert ticker_price(T(bid=100.0, ask=102.0, close=99.0)) == 101.0


def test_falls_back_to_the_close_when_nothing_else_is_live():
    """A paper account without a data subscription has only this."""
    assert ticker_price(T(close=2401.5)) == 2401.5


def test_a_one_sided_quote_is_not_half_used():
    assert ticker_price(T(bid=100.0, close=99.0)) == 99.0
    assert ticker_price(T(ask=102.0, close=99.0)) == 99.0


def test_a_crossed_quote_is_ignored():
    assert ticker_price(T(bid=105.0, ask=100.0, close=99.0)) == 99.0


def test_zero_and_negative_are_not_prices():
    assert ticker_price(T(last=0.0, close=50.0)) == 50.0
    assert ticker_price(T(last=-1.0, close=50.0)) == 50.0


def test_nothing_usable_returns_none_not_a_fake_price():
    assert ticker_price(T()) is None
    assert ticker_price(T(last=0.0, bid=0.0, ask=0.0, close=0.0)) is None


def test_market_price_is_used_when_it_is_the_only_source():
    assert ticker_price(T(mp=77.5)) == 77.5


def test_a_raising_market_price_does_not_break_the_loop():
    assert ticker_price(T(mp="raise", close=42.0)) == 42.0


def test_tolerates_a_ticker_missing_fields_entirely():
    class Bare:
        pass
    assert ticker_price(Bare()) is None
