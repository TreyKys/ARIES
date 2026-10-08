#!/usr/bin/env python3
"""Does floor-aware sizing solve the prop-account survival problem?

Rule tested: risk in proportion to the distance between equity and the kill
line, target_vol = k * (equity - floor) / equity. Far from the line, bigger;
near it, smaller. Profits widen the gap, so size grows on its own.

RESULT: it solves SURVIVAL completely (0 deaths in 4,000 bootstrapped 3-year
paths at k<=1.0, target still touched 56% of the time) and does NOT solve
EARNING (median return falls to ~0%/yr). Sizing down after a loss is a ratchet:
smaller size slows the recovery, so the survival guarantee is paid for out of
the return.

The cap is arithmetic, and the simulation matches it:
    sustainable return ~= edge_quality * room / bad_streak_multiple
                        = 0.49 * 6% / 2.5 = 1.2%/yr
against 1.15% measured at the size where only 0.4% of accounts die. Earning
10%/yr under a 6% rule needs quality ~4, which only market-neutral carry
reaches here (~3.5), and carry needs the spot leg prop firms do not offer.

Practical consequence: use DIFFERENT sizing per phase. An evaluation is a
retryable fee, so constant ~6% vol is right there (64% pass, 25% bust). A
funded account is not retryable, so floor-aware sizing is right there.
"""
import numpy as np, sys, csv
sys.path.insert(0,'/home/user/ARIES')

# real daily returns of the best honest config (wide tsmom), re-derived
from ares.tsmom import build_panel
from ares.factors import run_factor
import glob, os
EXCLUDE={"US10Y","US5Y","US30Y"}
names=sorted({os.path.basename(p)[:-4] for p in glob.glob('data/daily/*.csv')}-EXCLUDE)
led=run_factor(build_panel(names).loc['2000':],['tsmom'],target_markets=len(names))
eq=np.array([e for _,e in led.curve]); R=np.diff(eq)/eq[:-1]; R=R[np.isfinite(R)]
S=(R.mean()*252)/(R.std()*np.sqrt(252)); V=R.std()*np.sqrt(252)
print(f"strategy: Sharpe {S:.2f}, vol {V*100:.1f}%, {len(R)} days")

g=np.random.default_rng(42)
def boot(n,blk=20):
    o=[]
    while len(o)<n: 
        i=g.integers(0,len(R)-blk); o.extend(R[i:i+blk])
    return np.array(o[:n])

def unitised(n):
    """bootstrapped path standardised to unit vol, carrying real fat tails"""
    x=boot(n); return (x-x.mean())/x.std()

def sim(mode, k, days=756, target=0.10, dd=0.06, locked=True, sharpe=None, gap_p=0.0):
    sh = S if sharpe is None else sharpe
    z=unitised(days)
    e=1.0; peak=1.0; floor=1.0-dd
    passed=False
    for t in range(days):
        if locked: fl=max(floor, 1.0-dd)          # static/locked at start-6%
        else:      fl=peak-dd                      # trailing
        room=max(e-fl, 0.0)
        if mode=='const':
            vol=k
        else:
            vol=k*room/e if e>0 else 0.0
        dmu=sh*vol/252; dsd=vol/np.sqrt(252)
        r=z[t]*dsd+dmu
        if gap_p>0 and g.random()<gap_p:           # overnight gap risk
            r-= abs(g.normal(0,3*dsd))
        e*=(1+r)
        peak=max(peak,e)
        if e<=fl: return ('dead', t, e)
        if not passed and e>=1+target: passed=True
    return ('passed' if passed else 'alive', days, e)

print(f"\n3-year outcomes, 4000 paths, 10% target / 6% locked floor")
print(f"{'sizing':28s}{'died':>7s}{'passed':>8s}{'end eq':>9s}{'median ret/yr':>15s}")
print('-'*68)
for lab,mode,k in (('constant 2.4% vol','const',0.024),
                   ('constant 6% vol','const',0.06),
                   ('constant 10% vol','const',0.10),
                   ('FLOOR-AWARE k=0.4','floor',0.4),
                   ('FLOOR-AWARE k=1.0','floor',1.0),
                   ('FLOOR-AWARE k=2.0','floor',2.0),
                   ('FLOOR-AWARE k=4.0','floor',4.0)):
    out=[sim(mode,k) for _ in range(4000)]
    dead=np.mean([o[0]=='dead' for o in out])*100
    pas=np.mean([o[0]=='passed' for o in out])*100
    ends=np.array([o[2] for o in out])
    med=(np.median(ends)**(1/3)-1)*100
    print(f"{lab:28s}{dead:6.1f}%{pas:7.1f}%{np.median(ends):9.3f}{med:14.2f}%")
