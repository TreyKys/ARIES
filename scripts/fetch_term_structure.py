#!/usr/bin/env python3
"""Fetch futures TERM STRUCTURE (contracts 1-4) from the EIA.

This is the dataset that makes calendar-spread carry validatable. Yahoo is no
use here: dated contracts (CLZ25.NYM etc.) 404 once expired, so there is no
history. The EIA publishes daily settlements for the nearest four NYMEX
contracts, keyless, with decades of history:

    WTI crude   RCLC1..4   (pet)   1985-> ~9,200 rows
    Nat gas     RNGC1..4   (ng)    1994-> ~7,100 rows

    python scripts/fetch_term_structure.py
"""
import sys
import urllib.request
from pathlib import Path

import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FAMILIES = {"RCLC": "pet", "RNGC": "ng"}
OUT = Path("data/term")


def grab(series: str, section: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{series}.xls"
    url = f"https://www.eia.gov/dnav/{section}/hist_xls/{series}d.xls"
    req = urllib.request.Request(url, headers=UA)
    dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return dest


def column(series: str, section: str) -> pd.Series:
    path = grab(series, section)
    x = pd.read_excel(path, sheet_name=1, skiprows=2, engine="xlrd")
    x.columns = ["date", "px"]
    x["date"] = pd.to_datetime(x["date"])
    return x.set_index("date")["px"].astype(float).dropna()


def main() -> int:
    for pre, section in FAMILIES.items():
        try:
            panel = pd.DataFrame({f"C{i}": column(f"{pre}{i}", section)
                                  for i in (1, 2, 3, 4)}).dropna()
        except Exception as e:  # noqa: BLE001
            print(f"{pre}: FAILED ({type(e).__name__}: {e})", file=sys.stderr)
            continue
        out = OUT / f"{pre}_panel.csv"
        panel.to_csv(out)
        print(f"Wrote {out}: {len(panel)} rows "
              f"{panel.index[0].date()} -> {panel.index[-1].date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
