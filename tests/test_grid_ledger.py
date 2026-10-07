import math

from ares.grid_ledger import run_grid
from ares.ledger import summarise

TS = [i * 3600_000 for i in range(4000)]


def test_grid_harvests_oscillation():
    px = [100 + 8 * math.sin(i / 5.0) for i in range(4000)]
    led = run_grid(TS, px, capital=50.0, spacing_pct=0.01, max_inventory=20, cost_bps=0.0)
    assert len(led.fills) > 100
    assert summarise(led, periods_per_year=24 * 365).ann_return_pct > 0


def test_slow_decline_actually_triggers_buys():
    """Regression: the ladder reference must ratchet UP only while flat.

    Resetting it to price every bar (the obvious way to keep the ladder near the
    market) silently disables the strategy -- a buy then needs a full spacing
    move inside ONE bar. With 0.05%/bar steps and 1% spacing, price fell 86%
    and the grid took ZERO fills while reporting a tidy 0.00% return.
    """
    px = [100 * (0.9995 ** i) for i in range(4000)]      # -86% over the sample
    led = run_grid(TS, px, capital=50.0, spacing_pct=0.01, max_inventory=20, cost_bps=0.0)
    assert len(led.fills) > 0                             # it must engage
    assert summarise(led, periods_per_year=24 * 365).ann_return_pct < 0   # and lose honestly


def test_grid_never_uses_leverage_it_does_not_have():
    px = [100 * (0.999 ** i) for i in range(4000)]
    led = run_grid(TS, px, capital=50.0, spacing_pct=0.005, max_inventory=200, cost_bps=0.0)
    assert led.cash >= -1e-9                              # never spends cash it lacks
    assert led.equity() >= -1e-9


def test_bag_is_marked_at_real_price_not_cost():
    # Buy one rung then let price halve: equity must fall by the real loss.
    px = [100.0, 98.0] + [50.0] * 10
    ts = [i * 3600_000 for i in range(len(px))]
    led = run_grid(ts, px, capital=50.0, spacing_pct=0.01, max_inventory=20, cost_bps=0.0)
    assert led.pos.get("ASSET", 0.0) > 0
    assert led.equity() < 50.0
