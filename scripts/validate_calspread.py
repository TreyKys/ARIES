#!/usr/bin/env python3
"""Validate the calendar-spread carry hypothesis on 30-40yr of EIA term
structure, with a strict IS/OOS split and placebo controls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from ares.calspread import backtest_calspread, cl_expiries, ng_expiries

MKT = {'WTI crude (CL)': ('data/term/RCLC_panel.csv', cl_expiries),
       'Nat gas (NG)':   ('data/term/RNGC_panel.csv', ng_expiries)}

def show(tag, r):
    print(f"    {tag:22s} ret {r.ann_return_pct:+7.2f}%/yr  vol {r.ann_vol_pct:5.2f}%  "
          f"Sharpe {r.sharpe:+5.2f}  maxDD {r.max_drawdown_pct:5.2f}%  hit {r.hit_rate_pct:4.1f}%  n={r.days}")

for name,(path,expfn) in MKT.items():
    d = pd.read_csv(path, index_col=0, parse_dates=True)
    exp = expfn(d.index[0].year, d.index[-1].year)
    k = int(len(d)*0.6)
    IS, OOS = d.iloc[:k], d.iloc[k:]
    print(f"\n{'='*92}\n{name}: {d.index[0].date()} -> {d.index[-1].date()}  "
          f"IS to {IS.index[-1].date()} | OOS from {OOS.index[0].date()}\n{'='*92}")
    for leg in (('C1','C2'),('C1','C3'),('C1','C4')):
        print(f"  spread {leg[0]}-{leg[1]}:")
        for tag, seg in (('IN-SAMPLE',IS), ('OUT-OF-SAMPLE',OOS)):
            r = backtest_calspread(seg, exp, near=leg[0], far=leg[1])
            show(tag, r)
        inv = backtest_calspread(OOS, exp, near=leg[0], far=leg[1], signal='inverted')
        show('OOS placebo:inverted', inv)
        rs = [backtest_calspread(OOS, exp, near=leg[0], far=leg[1], signal='random',
                                 rng=np.random.default_rng(s)).ann_return_pct for s in range(30)]
        print(f"    {'OOS placebo:random':22s} ret {np.mean(rs):+7.2f}%/yr "
              f"(30 seeds, sd {np.std(rs):.2f}, best {max(rs):+.2f})")
