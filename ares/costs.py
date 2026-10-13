"""Per-contract trading costs, as a futures account actually pays them.

Why this replaces a flat basis-point rate. Futures commissions are charged
PER CONTRACT, in dollars, not as a percentage of notional. So the cost of a
trade in basis points is commission / notional, and it varies by a factor of
several across the micros: a micro crude contract (~$6,500 of oil) pays almost
the same dollar commission as a micro Nasdaq contract (~$42,000), and therefore
about six times as much per dollar traded. A flat bp rate hides exactly the
thing worth optimising.

Round trip = 2 x commission + one full spread. Crossing a one-tick spread
costs half a tick on the way in and half on the way out.

Commission figures are Phidias's published schedule (phidiaspropfirm.com/rules,
read 2026-10-13), Tradovate/NinjaTrader column unless noted. The firm says
they are indicative and may change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ContractCost:
    commission_side: float   # USD per contract per side
    tick: float              # minimum price increment
    mult: float              # USD per 1.0 of price
    spread_ticks: float = 1.0

    @property
    def tick_value(self) -> float:
        return self.tick * self.mult

    def round_trip_usd(self) -> float:
        return 2.0 * self.commission_side + self.spread_ticks * self.tick_value

    def side_usd(self) -> float:
        """Cost of ONE trade (one side): commission plus half the spread."""
        return self.commission_side + 0.5 * self.spread_ticks * self.tick_value

    def round_trip_bp(self, price: float) -> float:
        return self.round_trip_usd() / (price * self.mult) * 1e4


# Phidias, Tradovate/NinjaTrader schedule.
PHIDIAS_TRADOVATE: Dict[str, ContractCost] = {
    "MES": ContractCost(0.75, 0.25, 5.0),
    "MNQ": ContractCost(0.75, 0.25, 2.0),
    "MYM": ContractCost(0.75, 1.0, 0.5),
    "M2K": ContractCost(0.75, 0.10, 5.0),
    "MGC": ContractCost(1.10, 0.10, 10.0),
    "SIL": ContractCost(1.50, 0.005, 1000.0),
    "MCL": ContractCost(0.90, 0.01, 100.0),
    "M6E": ContractCost(0.64, 0.0001, 12500.0),
    "M6A": ContractCost(0.64, 0.0001, 10000.0),
    "M6B": ContractCost(0.64, 0.0001, 6250.0),
    "MBT": ContractCost(1.55, 5.0, 0.1),
    "MET": ContractCost(0.50, 0.50, 0.1),
}

# Phidias, Rithmic schedule. Cheaper for MGC/SIL, dearer for FX.
PHIDIAS_RITHMIC: Dict[str, ContractCost] = {
    "MES": ContractCost(0.79, 0.25, 5.0),
    "MNQ": ContractCost(0.79, 0.25, 2.0),
    "MYM": ContractCost(0.79, 1.0, 0.5),
    "M2K": ContractCost(0.79, 0.10, 5.0),
    "MGC": ContractCost(0.94, 0.10, 10.0),
    "SIL": ContractCost(0.94, 0.005, 1000.0),
    "MCL": ContractCost(0.94, 0.01, 100.0),
    "M6E": ContractCost(0.94, 0.0001, 12500.0),
    "M6A": ContractCost(0.94, 0.0001, 10000.0),
    "MBT": ContractCost(2.86, 5.0, 0.1),
    "MET": ContractCost(0.98, 0.50, 0.1),
}

# Full-size contracts, for comparison: ten times the notional of a micro for
# roughly three times the commission.
FULL_SIZE_TRADOVATE: Dict[str, ContractCost] = {
    "ES": ContractCost(2.68, 0.25, 50.0),
    "NQ": ContractCost(2.68, 0.25, 20.0),
    "GC": ContractCost(2.95, 0.10, 100.0),
    "CL": ContractCost(2.80, 0.01, 1000.0),
}


def cheapest(sym: str) -> ContractCost:
    """The lower round-trip of the two Phidias schedules for a symbol."""
    a, b = PHIDIAS_TRADOVATE.get(sym), PHIDIAS_RITHMIC.get(sym)
    if a is None:
        return b
    if b is None:
        return a
    return a if a.round_trip_usd() <= b.round_trip_usd() else b
