#!/usr/bin/env python3
"""Does ARES get smarter by learning? Test it honestly.

1. Collect every breakout setup on 2024 data (ETH/SOL/AVAX/LINK 4h) and
   label each by its real outcome (win/loss).
2. Train a classifier to estimate P(win) from the setup's features.
3. On 2025 data it has NEVER seen, compare the strategy WITH the learned
   filter vs WITHOUT it. If learning helps, the filtered profit factor is
   higher on unseen data. If it doesn't, we say so.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ares import datasource, indicators
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PAIRS = ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]
SPLIT = 1735689600000  # 2025-01-01
CH, ATR_MULT, RR = 55, 2.0, 2.0
FEE, SLIP = 0.0005, 0.0005


def features_and_setups(candles):
    """Return (feature_matrix, setup_indices, arrays) with no lookahead."""
    o = np.array([c.open for c in candles]); h = np.array([c.high for c in candles])
    l = np.array([c.low for c in candles]); c_ = np.array([c.close for c in candles])
    import pandas as pd
    don_hi = pd.Series(h).rolling(CH).max().shift(1).to_numpy()
    atr = indicators.atr(h, l, c_, 14)
    rsi = indicators.rsi(c_, 14)
    ema21 = indicators.ema(c_, 21); ema55 = indicators.ema(c_, 55)
    ret1 = np.concatenate(([0], np.diff(c_) / c_[:-1]))
    ret5 = np.concatenate((np.zeros(5), (c_[5:] - c_[:-5]) / c_[:-5]))
    ret20 = np.concatenate((np.zeros(20), (c_[20:] - c_[:-20]) / c_[:-20]))
    feats = np.column_stack([
        rsi, atr / c_, (ema21 - ema55) / c_, ret1, ret5, ret20,
    ])
    return feats, (o, h, l, c_, don_hi, atr)


def collect(candles):
    """Yield (feature_row, label, r_multiple) for each resolved breakout."""
    feats, (o, h, l, c_, don_hi, atr) = features_and_setups(candles)
    n = len(candles)
    i = 57
    rows = []
    while i < n - 1:
        if np.isnan(don_hi[i]) or np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(feats[i]).any():
            i += 1; continue
        if c_[i] > don_hi[i]:                       # breakout long
            entry = c_[i] * (1 + SLIP)
            stop = c_[i] - ATR_MULT * atr[i]
            risk = entry - stop
            tp = entry + RR * risk
            label, rmult, exit_i = None, None, i
            for j in range(i + 1, n):
                if l[j] <= stop:
                    label, rmult, exit_i = 0, -(1 + (FEE * 2 * entry) / risk), j; break
                if h[j] >= tp:
                    label, rmult, exit_i = 1, RR - (FEE * 2 * entry) / risk, j; break
            if label is not None:
                rows.append((feats[i], label, rmult))
                i = exit_i + 1
                continue
        i += 1
    return rows


def pf_and_exp(rmults):
    wins = sum(r for r in rmults if r > 0)
    losses = -sum(r for r in rmults if r <= 0)
    pf = wins / losses if losses > 0 else float("inf")
    return pf, (sum(rmults) / len(rmults) if rmults else 0.0), len(rmults)


def main() -> int:
    # ---- build train (2024) and test (2025) sets, pooled across pairs ----
    train, test = [], []
    for sym in PAIRS:
        rows = datasource.load_csv(f"data/{sym}_4h.csv")
        train += collect([c for c in rows if c.ts < SPLIT])
        test += collect([c for c in rows if c.ts >= SPLIT])

    Xtr = np.array([r[0] for r in train]); ytr = np.array([r[1] for r in train])
    Xte = np.array([r[0] for r in test]); yte = np.array([r[1] for r in test])
    rte = [r[2] for r in test]

    print(f"train setups: {len(train)}  (win rate {ytr.mean():.1%})")
    print(f"test  setups: {len(test)}   (win rate {yte.mean():.1%})")

    model = GradientBoostingClassifier(max_depth=2, n_estimators=120, learning_rate=0.05)
    model.fit(Xtr, ytr)
    ptr = model.predict_proba(Xtr)[:, 1]
    pte = model.predict_proba(Xte)[:, 1]
    print(f"train AUC {roc_auc_score(ytr, ptr):.3f}  |  test AUC {roc_auc_score(yte, pte):.3f}")

    # threshold chosen on TRAIN (median predicted prob) -> applied to TEST
    thr = float(np.quantile(ptr, 0.5))

    base_pf, base_exp, base_n = pf_and_exp(rte)
    keep = pte >= thr
    filt_pf, filt_exp, filt_n = pf_and_exp([rte[i] for i in range(len(rte)) if keep[i]])

    print("-" * 60)
    print(f"OOS 2025  WITHOUT learning: PF={base_pf:.2f}  exp={base_exp:+.3f}R  trades={base_n}")
    print(f"OOS 2025  WITH ML filter  : PF={filt_pf:.2f}  exp={filt_exp:+.3f}R  trades={filt_n}")
    print("-" * 60)
    verdict = "HELPS" if filt_pf > base_pf else "does NOT help"
    print(f"Verdict: learning {verdict} out-of-sample "
          f"(PF {base_pf:.2f} -> {filt_pf:.2f}). AUC>0.5 means real signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
