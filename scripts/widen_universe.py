#!/usr/bin/env python3
"""Does widening the universe raise the book's Sharpe? Measure it.

The prop-firm study (docs/PROP_FIRMS.md) showed the gate needs about Sharpe
1.2 and the book measures 0.41 on the eight micro futures it currently
trades. The same strategy measured 0.84 over 57 years on a wider daily
universe, so breadth is the one lever with a theoretical reason to work:
for N uncorrelated return streams, portfolio Sharpe scales with sqrt(N).
Breadth is also the only improvement that is not a fitted parameter.

DISCIPLINE. The tiers below are committed in advance and each is defined by a
RULE -- "every CME-group micro contract", "every mini grain" -- never by
picking markets that happened to help. Each tier is reported whether it
helped or not. Searching over subsets of 20 markets would find a wonderful
backtest and nothing else.

Two separate questions, deliberately measured apart:
  1. Does breadth raise the edge? Run at $1,000,000, where whole-contract
     granularity does not bind, so the answer is about diversification only.
  2. Can a real account hold it? Re-run at $50k-150k, where granularity and
     margin bite, and most of the theoretical gain may not survive.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ares.combined_backtest import backtest           # noqa: E402
from ares.ledger import summarise            # noqa: E402


@dataclass(frozen=True)
class Market:
    sym: str          # exchange symbol of the contract actually traded
    data: str         # daily history file in data/daily
    mult: float       # contract multiplier (provisional; see docs)
    sign: int         # +1, or -1 where the data series is quoted the other way
    margin: float     # rough overnight margin, USD
    group: str


# Tier 1: what the runner trades today.
T1 = [
    Market("MES", "SPX",     5.0,      +1, 2400, "equity"),
    Market("MNQ", "NDX",     2.0,      +1, 3100, "equity"),
    Market("MYM", "DJI",     0.5,      +1, 1100, "equity"),
    Market("MGC", "GOLD",    10.0,     +1, 1200, "metals"),
    Market("SIL", "SILVER",  1000.0,   +1, 1400, "metals"),
    Market("MCL", "WTI",     100.0,    +1, 1400, "energy"),
    Market("M6E", "EURUSD",  12500.0,  +1,  300, "fx"),
    Market("M6A", "AUDUSD",  10000.0,  +1,  250, "fx"),
]

# Tier 2: every REMAINING CME-group micro contract for which we hold history.
# The two FX rows carry sign -1 because the data series is quoted USD-base
# (USD per CAD) while the futures contract is the other way round (CAD per
# USD). Trading the series unflipped would hold exactly the wrong position.
T2 = T1 + [
    Market("M2K", "RUSSELL", 5.0,      +1,  900, "equity"),
    Market("MHG", "COPPER",  2500.0,   +1,  700, "metals"),
    Market("MNG", "NATGAS",  1000.0,   +1,  500, "energy"),
    Market("M6B", "GBPUSD",  6250.0,   +1,  350, "fx"),
    Market("MJY", "USDJPY",  1250000.0, -1,  300, "fx"),
    Market("MCD", "USDCAD",  10000.0,  -1,  250, "fx"),
]

# Tier 3: the mini grains at CBOT (1,000 bushels, one fifth of the full
# contract). Priced in cents, so the multiplier is $10 per cent.
T3 = T2 + [
    Market("XC", "CORN",     10.0,     +1,  400, "grains"),
    Market("XW", "WHEAT",    10.0,     +1,  500, "grains"),
    Market("XK", "SOY",      10.0,     +1,  700, "grains"),
]

# Tier 4: CME micro crypto. Short history (2014 / 2017), so these contribute
# only to recent years -- which is the half of the sample that matters most
# for a decision about the future.
T4 = T3 + [
    Market("MBT", "BITCOIN", 0.1,      +1, 1800, "crypto"),
    Market("MET", "ETHER",   0.1,      +1, 1100, "crypto"),
]

# The decisive diagnostic: the ADDED markets on their own. sqrt(N)
# diversification only pays if each added stream carries its own edge. If this
# book measures near zero, breadth is diluting rather than diversifying, and
# no amount of re-weighting fixes that.
ADDED = [m for m in T4 if m not in T1]

# Everything in data/daily, tradeable or not. This is NOT a candidate book --
# most of it cannot be traded at micro size by a small account. It exists to
# test the breadth hypothesis at its theoretical maximum, and to check a claim
# this project has been repeating: that the same strategy measured 0.84 on a
# wider universe. If the full panel also measures ~0.5 over 2000-2026, then
# that 0.84 came from the ERA (57 years, dominated by the 1970s-90s), not from
# breadth, and the claim needs correcting.
ALL60 = [Market(p.stem, p.stem, 1.0, +1, 0, "research")
         for p in sorted(Path("data/daily").glob("*.csv"))]

TIERS = {"T1 current 8": T1, "T2 +CME micros": T2,
         "T3 +mini grains": T3, "T4 +micro crypto": T4,
         "ADDED only (11)": ADDED, "ALL (research only)": ALL60}


def load_panel(markets, folder="data/daily") -> pd.DataFrame:
    cols = {}
    for m in markets:
        p = Path(folder) / f"{m.data}.csv"
        if not p.exists():
            print(f"  ! missing {p}", file=sys.stderr)
            continue
        d = pd.read_csv(p)
        s = pd.Series(d["close"].values,
                      index=pd.to_datetime(d["ts"], unit="ms"))
        s = s[~s.index.duplicated(keep="last")].sort_index()
        s = s[s > 0]
        # Invert rather than negate: a futures contract quoted the other way
        # round IS the reciprocal series, exactly, not the mirrored one.
        cols[m.sym] = (1.0 / s) if m.sign < 0 else s
    px = pd.DataFrame(cols).sort_index().ffill()
    # Blank implausible daily moves AND their neighbours. Continuous series
    # carry roll discontinuities, and the reversal leg would otherwise profit
    # from both the artificial jump and its mirror image the next day.
    r = px.pct_change()
    bad = r.abs() > 0.25
    bad = bad | bad.shift(-1).fillna(False) | bad.shift(1).fillna(False)
    keep = max(4, int(len(px.columns) * 0.5))
    return px.mask(bad).dropna(axis=0, thresh=keep)


def common_window(tiers) -> tuple:
    """The date range every tier can cover.

    Without this the comparison is void: T2 adds Russell (1987) and T4 adds
    bitcoin (2014), and the 50%-coverage rule then starts each tier on a
    different day. Comparing Sharpes measured over different decades says
    nothing about breadth.
    """
    lo, hi = None, None
    for mk in tiers.values():
        px = load_panel(mk)
        lo = px.index[0] if lo is None else max(lo, px.index[0])
        hi = px.index[-1] if hi is None else min(hi, px.index[-1])
    return lo, hi


def report(name, led, px, extra=""):
    s = summarise(led)
    eq = np.array([e for _, e in led.curve], float)
    ts = np.array([t for t, _ in led.curve], float)
    r = np.diff(eq) / eq[:-1]
    half = len(r) // 2
    def sh(x):
        return (x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() else 0.0
    print(f"  {name:18s} {len(px.columns):3d} mkts  {px.index[0].date()}"
          f"->{px.index[-1].date()}  {s.ann_return_pct:+6.2f}%/yr"
          f"  vol {s.ann_vol_pct:5.2f}%  Sharpe {s.sharpe:+5.2f} +/-{s.sharpe_stderr:4.2f}"
          f"  (t={s.sharpe_t:+5.2f})  DD {s.max_drawdown_pct:5.1f}%"
          f"  IS {sh(r[:half]):+5.2f} OOS {sh(r[half:]):+5.2f} {extra}")
    return s


def decades(led):
    eq = np.array([e for _, e in led.curve], float)
    ts = pd.to_datetime(np.array([t for t, _ in led.curve]), unit="ms")
    r = pd.Series(np.diff(eq) / eq[:-1], index=ts[1:])
    out = []
    for dec, grp in r.groupby((r.index.year // 10) * 10):
        if len(grp) > 200:
            out.append(f"{dec}s {grp.mean()/grp.std()*np.sqrt(252):+.2f}")
    return "  ".join(out)


def diagnose(tiers, lo, hi, capital, target_vol, max_contracts) -> None:
    """Which leg degrades as the universe grows, and is top_k the confound?

    The reversal leg trades top_k longs and top_k shorts REGARDLESS of how
    many markets exist, while the trend leg takes a position in every market.
    So as N grows, a fixed top_k silently rebalances the book away from
    reversal and towards trend. That is a change in the strategy, not a test
    of breadth, and it has to be ruled out before concluding anything.
    """
    print("\n  leg isolation (same days, uncapped) — Sharpe (IS / OOS)")
    print("  " + "-" * 104)
    print(f"  {'tier':18s} {'N':>3} {'trend only':>22} {'reversal only':>22}"
          f" {'50/50 k=3':>22} {'50/50 k=N//3':>22}")
    for name, mk in tiers.items():
        px = load_panel(mk).loc[lo:hi]
        mult = {m.sym: m.mult for m in mk if m.sym in px.columns}
        n = len(px.columns)
        cells = []
        for w, k in ((1.0, 3), (0.0, 3), (0.5, 3), (0.5, max(3, n // 3))):
            led = backtest(px, mult, capital=capital, target_vol=target_vol,
                           w_trend=w, top_k=k, max_contracts=max_contracts)
            eq = np.array([e for _, e in led.curve], float)
            r = np.diff(eq) / eq[:-1]
            h = len(r) // 2
            f = lambda x: ((x.mean() / x.std() * np.sqrt(252))
                           if len(x) > 2 and x.std() else 0.0)
            cells.append(f"{f(r):+5.2f} ({f(r[:h]):+5.2f}/{f(r[h:]):+5.2f})")
        print(f"  {name:18s} {n:3d} " + " ".join(f"{c:>22}" for c in cells))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=1_000_000.0)
    ap.add_argument("--target-vol", type=float, default=0.03)
    ap.add_argument("--top-k", type=int, default=3)
    # The per-market cap exists to stop one market dominating a small
    # account. At research capital it must NOT bind, or the book runs
    # under-risked and every tier is measured at the wrong volatility --
    # which is exactly what the first run of this study did (1.11% realised
    # against a 3% target).
    ap.add_argument("--max-contracts", type=int, default=100_000)
    ap.add_argument("--no-align", action="store_true",
                    help="skip the common date window (not comparable)")
    ap.add_argument("--decades", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--vol-window", type=int, default=0,
                    help="rank the reversal leg on vol-normalised moves "
                         "using this trailing window (0 = raw returns)")
    ap.add_argument("--scale-k", action="store_true",
                    help="scale top_k with the universe size (N//3)")
    a = ap.parse_args()
    print(f"\ncapital ${a.capital:,.0f} | vol target {a.target_vol*100:.0f}% "
          f"| top_k {'N//3' if a.scale_k else a.top_k} "
          f"| reversal ranking {'z-score/' + str(a.vol_window) + 'd' if a.vol_window else 'raw returns'}")
    print("=" * 118)
    lo = hi = None
    if not a.no_align:
        lo, hi = common_window(TIERS)
        print(f"common window {lo.date()} -> {hi.date()} "
              f"(every tier measured over the same days)")
        print("=" * 118)
    for name, mk in TIERS.items():
        px = load_panel(mk)
        if lo is not None:
            px = px.loc[lo:hi]
        mult = {m.sym: m.mult for m in mk if m.sym in px.columns}
        k = max(3, len(px.columns) // 3) if a.scale_k else a.top_k
        led = backtest(px, mult, capital=a.capital, target_vol=a.target_vol,
                       top_k=k, max_contracts=a.max_contracts,
                       vol_window=a.vol_window)
        s = report(name, led, px,
                   extra=f" margin ${sum(m.margin for m in mk):,.0f}")
        if a.decades:
            print(f"  {'':18s}     {decades(led)}")
    if a.diagnose and lo is not None:
        diagnose(TIERS, lo, hi, a.capital, a.target_vol, a.max_contracts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
