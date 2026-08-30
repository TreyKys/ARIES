"""Meta-label model: given a candidate setup's features, estimate P(win).

This is the "Historian done right" -- not a fake vector lookup, but a
trained classifier over real features and real trade outcomes. The
strategy uses its output only to *filter/size* trades it already found
(meta-labelling); it never invents trades on its own.

Right now this is a scaffold: no model file -> ``load_model`` returns
None, and the strategy runs exactly as it does today. When a real model
is trained (see ``ares/ml/train.py``, TODO) it is dumped to disk and
loaded here; ``predict_series`` then fills ``FeatureBundle.ml_win_prob``.
"""
from __future__ import annotations

import os
from typing import List, Optional, Protocol

import numpy as np


# Feature columns the model consumes, in a fixed order. Kept explicit so
# training and inference can never silently disagree on the layout.
FEATURE_COLUMNS: List[str] = [
    "ema_gap",        # (ema_fast - ema_slow) / close
    "rsi",
    "atr_pct",        # atr / close
    "ret_1",          # 1-bar return
    "ret_5",          # 5-bar return
]


def build_feature_matrix(fb) -> np.ndarray:
    """Assemble the model input matrix from a FeatureBundle (one row/bar)."""
    close = fb.close
    ema_gap = (fb.ema_fast - fb.ema_slow) / np.where(close == 0, np.nan, close)
    atr_pct = fb.atr / np.where(close == 0, np.nan, close)
    ret_1 = np.concatenate(([0.0], np.diff(close) / close[:-1]))
    ret_5 = np.concatenate((np.zeros(5), (close[5:] - close[:-5]) / close[:-5]))
    return np.column_stack([ema_gap, fb.rsi, atr_pct, ret_1, ret_5])


class Model(Protocol):
    def predict_series(self, fb) -> np.ndarray: ...


class MetaLabelModel:
    """Wraps a trained scikit-learn-style classifier with predict_proba."""

    def __init__(self, estimator):
        self.estimator = estimator

    def predict_series(self, fb) -> np.ndarray:
        X = build_feature_matrix(fb)
        proba = np.full(X.shape[0], np.nan)
        valid = ~np.isnan(X).any(axis=1)
        if valid.any():
            proba[valid] = self.estimator.predict_proba(X[valid])[:, 1]
        return proba


def load_model(path: str = "models/meta_label.pkl") -> Optional[MetaLabelModel]:
    """Load a trained model if present; otherwise None (strategy stays raw)."""
    if not path or not os.path.exists(path):
        return None
    import pickle
    with open(path, "rb") as f:
        estimator = pickle.load(f)
    return MetaLabelModel(estimator)
