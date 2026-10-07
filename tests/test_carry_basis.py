import numpy as np

from ares.carry_basis import (SPOT, PERP, CarryBasisConfig, choose_leverage,
                              run_carry_basis)
from ares.ledger import summarise

HOUR = 3600_000


def _flat(n=600, price=100.0, basis=0.0):
    ts = [i * HOUR for i in range(n)]
    spot = [price] * n
    perp = [price * (1 + basis)] * n
    return ts, spot, perp


def test_hedge_is_unit_matched_not_dollar_matched():
    """A basis trade must hold equal UNITS on both legs. Sizing each leg as
    notional/price gives spot qty != perp qty whenever perp != spot, leaving a
    hidden directional position that the 'hedge' does not cancel.
    """
    ts, spot, perp = _flat(basis=0.01)        # perp 1% above spot
    r = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                        cfg=CarryBasisConfig(dynamic=False, leverage_max=5.0))
    resid = r.ledger.pos.get(SPOT, 0.0) + r.ledger.pos.get(PERP, 0.0)
    assert abs(resid) < 1e-9


def test_widening_basis_is_a_loss_scaled_by_leverage():
    # perp climbs away from spot: short-perp leg loses more than spot gains.
    n = 400
    ts = [i * HOUR for i in range(n)]
    spot = [100.0] * n
    perp = [100.0 * (1 + 0.02 * i / n) for i in range(n)]   # basis 0 -> 2%
    lo = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                         cfg=CarryBasisConfig(dynamic=False, leverage_max=1.0))
    hi = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                         cfg=CarryBasisConfig(dynamic=False, leverage_max=5.0))
    assert hi.ledger.equity() < lo.ledger.equity() < 50.0


def test_constant_DOLLAR_basis_cancels_the_price_level():
    # Both legs move together with a fixed dollar gap: only fees should bite.
    n = 400
    ts = [i * HOUR for i in range(n)]
    spot = [100.0 * (1.01 ** i) for i in range(n)]          # +300%
    perp = [s + 0.05 for s in spot]                          # dollar gap fixed
    r = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                        cfg=CarryBasisConfig(dynamic=False, leverage_max=5.0))
    assert abs(r.ledger.equity() - (50.0 - r.ledger.fees_paid)) < 0.05


def test_constant_PERCENT_basis_is_a_real_loss_in_a_rising_market():
    """Subtle and economically real: holding the basis constant as a FRACTION
    means the DOLLAR gap widens as price rises, and the dollar gap is what the
    two legs actually net to.

    Long 1 spot at 100, short 1 perp at 100.05. Price doubles: spot +100, the
    short loses -(200.10 - 100.05) = -100.05. Net -0.05 -- exactly the growth
    in the dollar gap. So a carry position bleeds slightly in a strong rally
    even with a 'constant' basis, on top of fees.
    """
    n = 400
    ts = [i * HOUR for i in range(n)]
    spot = [100.0 * (1.01 ** i) for i in range(n)]
    perp = [s * 1.0005 for s in spot]                        # fraction fixed
    r = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                        cfg=CarryBasisConfig(dynamic=False, leverage_max=5.0))
    beyond_fees = (50.0 - r.ledger.fees_paid) - r.ledger.equity()
    assert beyond_fees > 0.0          # a genuine loss, not a rounding artifact


def test_funding_is_credited_on_the_short_leg():
    ts, spot, perp = _flat()
    fund = {i * HOUR: 0.0001 for i in range(0, 600, 8)}
    paid = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                           cfg=CarryBasisConfig(dynamic=False, leverage_max=3.0))
    got = run_carry_basis(ts, spot, perp, fund, capital=50.0,
                          cfg=CarryBasisConfig(dynamic=False, leverage_max=3.0))
    assert got.funding_received > 0
    assert got.ledger.equity() > paid.ledger.equity()


def test_negative_funding_is_a_real_cost():
    ts, spot, perp = _flat()
    fund = {i * HOUR: -0.0005 for i in range(0, 600, 8)}
    r = run_carry_basis(ts, spot, perp, fund, capital=50.0,
                        cfg=CarryBasisConfig(dynamic=False, leverage_max=3.0))
    assert r.funding_received < 0
    assert r.ledger.equity() < 50.0


def test_breaker_fires_only_on_basis_dislocation():
    cfg = CarryBasisConfig(dynamic=True, mode="breaker")
    # calm basis -> full leverage, even when funding is negative (negative
    # funding is a small self-limiting cost; tying the breaker to it was the
    # churn source that cost $18.70 in fees over 6.7yr)
    assert choose_leverage(cfg, [0.0004], -0.001) == cfg.leverage_max
    # dislocated basis -> de-lever
    assert choose_leverage(cfg, [0.02], 0.0001) == cfg.leverage_min
    assert choose_leverage(cfg, [-0.02], 0.0001) == cfg.leverage_min


def test_leverage_never_escapes_the_configured_band():
    cfg = CarryBasisConfig(dynamic=True, mode="riskparity",
                           leverage_min=3.0, leverage_max=5.0)
    for vol in (1e-9, 1e-6, 1e-4, 1e-2, 1.0):
        lev = choose_leverage(cfg, [0.0] * 50 + [vol], 0.0001)
        assert 3.0 - 1e-9 <= lev <= 5.0 + 1e-9


def test_liquidation_is_modelled_and_stops_trading():
    # catastrophic basis blowout at high leverage must liquidate, not coast
    n = 300
    ts = [i * HOUR for i in range(n)]
    spot = [100.0] * n
    perp = [100.0 * (1 + 0.5 * i / n) for i in range(n)]     # basis -> 50%
    r = run_carry_basis(ts, spot, perp, {}, capital=50.0,
                        cfg=CarryBasisConfig(dynamic=False, leverage_max=5.0))
    assert r.liquidated
    assert r.ledger.pos.get(SPOT, 0.0) == 0.0
    assert r.ledger.pos.get(PERP, 0.0) == 0.0
