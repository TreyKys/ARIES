#!/usr/bin/env python3
"""Validate time-series momentum on 20-57yr of daily data via the audited ledger."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from ares.tsmom import build_panel, run_tsmom
from ares.ledger import summarise

NAMES = ["SPX","NDX","DJI","NKY","DAX","UKX","HSI","AS51",
         "EURUSD","USDJPY","GBPUSD","AUDUSD","USDCAD","USDCHF",
         "GOLD","SILVER","WTI","NATGAS","COPPER","CORN","SOY","WHEAT",
         "UST10","UST30"]          # US10Y dropped: a yield, not a tradeable price

px = build_panel(NAMES)
print(f"panel: {len(px)} days, {px.index[0].date()} -> {px.index[-1].date()} "
      f"({(px.index[-1]-px.index[0]).days/365.25:.1f}yr), {len(px.columns)} markets")
print(f"markets live at start: {int(px.iloc[0].notna().sum())}, at end: {int(px.iloc[-1].notna().sum())}\n")

print("FULL PERIOD (parameters from the literature, nothing fitted here)")
for sig in ("momentum","inverted"):
    s = summarise(run_tsmom(px, signal=sig))
    print(f"  {sig:9s} {s}")
rs=[summarise(run_tsmom(px, signal='random', rng=np.random.default_rng(k))) for k in range(8)]
print(f"  {'random':9s} ret {np.mean([x.ann_return_pct for x in rs]):+6.2f}%/yr  "
      f"Sharpe {np.mean([x.sharpe for x in rs]):+5.2f} (8 seeds, best {max(x.sharpe for x in rs):+.2f})")

print("\nSUB-PERIODS (is the documented post-2010 decay present?)")
for lo,hi in (("1970","1990"),("1990","2000"),("2000","2010"),("2010","2020"),("2020","2027")):
    seg = px.loc[lo:hi]
    if len(seg) < 400: continue
    s = summarise(run_tsmom(seg))
    print(f"  {lo}-{hi}  {s}")

print("\nCOST SENSITIVITY (full period)")
for bps in (0.0, 5.0, 10.0, 20.0, 40.0):
    s = summarise(run_tsmom(px, cost_bps=bps))
    print(f"  {bps:4.0f}bps  ret {s.ann_return_pct:+6.2f}%/yr  Sharpe {s.sharpe:+5.2f}  "
          f"fees ${s.fees_paid:,.0f}")
