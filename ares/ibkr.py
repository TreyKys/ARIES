"""Small IBKR helpers kept out of the runner so they can be tested.

Nothing here talks to IBKR. These are the two decisions that are easy to get
wrong and impossible to check once a connection is open: which port is the
LIVE one, and what counts as a usable price.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

# TWS and IB Gateway use different ports, and each has a live and a paper one.
# Getting this wrong is the difference between a simulation and real money.
PORTS = {
    7496: ("TWS", "live"),
    7497: ("TWS", "paper"),
    4001: ("IB Gateway", "live"),
    4002: ("IB Gateway", "paper"),
}


def classify_port(port: int) -> Tuple[str, str]:
    """(application, 'live' | 'paper' | 'unknown') for an API port."""
    return PORTS.get(port, ("unknown application", "unknown"))


def live_port_refusal(port: int, allow_live: bool) -> Optional[str]:
    """The message to abort with, or None if this port may be used.

    An unknown port is refused as well. The runner cannot tell whether a
    custom port is a paper or a live gateway, and a wrong guess here spends
    real money -- so it asks rather than assumes.
    """
    app, kind = classify_port(port)
    if kind == "live" and not allow_live:
        return (f"IB_PORT={port} is {app}'s LIVE trading port. This runner "
                f"refuses it unless you pass --allow-live.\n"
                f"Paper ports are 7497 (TWS) and 4002 (IB Gateway).")
    if kind == "unknown" and not allow_live:
        return (f"IB_PORT={port} is not a port this runner recognises, so it "
                f"cannot tell whether it is a paper or a live account.\n"
                f"Use 7497 (TWS paper) or 4002 (IB Gateway paper), or pass "
                f"--allow-live if you are certain.")
    return None


def ticker_price(t) -> Optional[float]:
    """Best usable price from an ib_insync/ib_async ticker, or None.

    A paper account usually has no real-time futures market data
    subscription, so `last` is nan and only delayed or close fields are
    populated. Taking `last` alone leaves the runner reporting "no live
    prices" forever with nothing explaining why.

    Order of preference: the last trade, then the midpoint of a two-sided
    quote, then the previous close. A one-sided or crossed quote is ignored
    rather than half-used.
    """
    def ok(v) -> Optional[float]:
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) and v > 0 else None

    cands = [ok(getattr(t, "last", None))]
    bid, ask = ok(getattr(t, "bid", None)), ok(getattr(t, "ask", None))
    if bid and ask and ask >= bid:
        cands.append((bid + ask) / 2)
    mp = getattr(t, "marketPrice", None)
    if callable(mp):
        try:
            cands.append(ok(mp()))
        except Exception:                                 # noqa: BLE001
            pass
    cands.append(ok(getattr(t, "close", None)))
    for p in cands:
        if p:
            return float(p)
    return None


def import_ib():
    """Import the IBKR client, preferring the maintained fork.

    ib_insync is no longer maintained; ib_async is the community continuation
    with the same API. Accept either so an existing install keeps working.
    """
    try:
        from ib_async import IB, Future, MarketOrder
        return IB, Future, MarketOrder, "ib_async"
    except ImportError:
        pass
    try:
        from ib_insync import IB, Future, MarketOrder
        return IB, Future, MarketOrder, "ib_insync"
    except ImportError:
        raise SystemExit(
            "--paper needs an IBKR client:\n"
            "    pip install ib_async        (maintained fork, preferred)\n"
            "    pip install ib_insync       (original, no longer maintained)\n"
            "You also need TWS or IB Gateway running, logged into a PAPER "
            "account, with API connections enabled.")
