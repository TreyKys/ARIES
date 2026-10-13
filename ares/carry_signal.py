"""Futures carry from the front and second contract, roll-adjusted.

Carry is the return a futures position earns if prices do not move -- the
slope of the curve. Koijen, Moskowitz, Pedersen & Vrugt, "Carry" (JFE 2018):
cross-sectional carry earns a premium across every asset class tested and is
largely independent of momentum and value. It is rebalanced monthly, so its
fee bill is small -- which is why it is the natural answer to a fee problem
that the one-day reversal edge cannot escape.

    carry = (F_near - F_far) / F_far / years_between_contracts

Positive carry = backwardation: the far contract is cheaper, so a long
position rolls up toward the near price over time. For a currency future it
is the interest-rate differential; for an index future, dividend yield minus
the financing rate; for a commodity, the convenience yield net of storage.

Two traps, both handled here rather than assumed away:
  * The gap between contracts differs by market (one month for crude, three
    for index and FX futures). It is measured from how often the front
    contract actually rolls, not hard-coded.
  * Returns from a continuous front-month series contain a jump at every
    roll. They are computed from the contract IDs instead: on a roll day the
    new front contract was yesterday's second contract, so the true return is
    front_today / second_yesterday - 1.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

FOLDER = Path("data/carry")


def load_root(root: str, folder: Path = FOLDER) -> pd.DataFrame:
    def one(i):
        d = pd.read_csv(folder / f"{root}_c{i}.csv")
        # Databento's CSV carries the event time as epoch seconds here.
        d["date"] = pd.to_datetime(d["date"].astype("int64"), unit="s").dt.normalize()
        d = d.drop_duplicates("date", keep="last").set_index("date")
        # Drop the Sunday-evening stub bar. Databento's daily bars are UTC
        # days, and Globex reopens on Sunday evening New York time, so each
        # week carries an extra 'day' an hour or two long: 16.4% of rows,
        # 311 sessions a year instead of 252. Left in, a daily strategy
        # ranks on a Friday-to-Sunday move and rebalances on a stub -- which
        # took the reversal book from +0.57 to 0.00 and inflated its
        # turnover. Dropping the row makes Monday's return Friday->Monday,
        # which is the session the strategy actually holds.
        d = d[d.index.dayofweek != 6]
        return d.rename(columns={"close": f"p{i}", "contract": f"id{i}",
                                 "volume": f"v{i}"})
    return one(0).join(one(1), how="inner").sort_index()


def roll_adjusted_returns(df: pd.DataFrame) -> pd.Series:
    """Daily return of holding the front contract, rolling into the second."""
    same = df["id0"] == df["id0"].shift(1)
    rolled = df["id0"] == df["id1"].shift(1)
    r = pd.Series(np.nan, index=df.index)
    r[same] = (df["p0"] / df["p0"].shift(1) - 1.0)[same]
    r[rolled] = (df["p0"] / df["p1"].shift(1) - 1.0)[rolled]
    # anything else (data gap across two rolls) stays NaN rather than guessed
    return r.where(r.abs() < 0.25)


def contract_gap_years(df: pd.DataFrame) -> float:
    """Years between consecutive contracts, from the observed roll frequency."""
    rolls = (df["id0"] != df["id0"].shift(1)).sum() - 1
    years = (df.index[-1] - df.index[0]).days / 365.25
    per_year = rolls / years if years > 0 else 4.0
    # snap to the listing cycles that exist, so one missing day of data does
    # not turn a quarterly contract into a 4.3-per-year one
    cycles = np.array([12.0, 6.0, 4.0])
    return 1.0 / cycles[np.argmin(np.abs(cycles - per_year))]


def raw_carry(df: pd.DataFrame, gap: float) -> pd.Series:
    distinct = df["id0"] != df["id1"]
    c = (df["p0"] - df["p1"]) / df["p1"] / gap
    return c.where(distinct & (df["p1"] > 0))


def load_panel(roots) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    rets, carry, gaps = {}, {}, {}
    for r in roots:
        df = load_root(r)
        g = contract_gap_years(df)
        gaps[r] = g
        rets[r] = roll_adjusted_returns(df)
        carry[r] = raw_carry(df, g)
    R = pd.DataFrame(rets).sort_index()
    K = pd.DataFrame(carry).reindex(R.index)
    return R, K, gaps
