"""Sources of OHLCV data for backtests.

- ``generate_candles``: deterministic synthetic data for tests/demos.
- ``load_csv``: read a real dataset saved to disk.
- ``fetch_ohlcv``: best-effort pull from an exchange via ccxt (run on the
  VPS where the exchange is reachable; not required for tests).
"""
from __future__ import annotations

import csv
from typing import List

import numpy as np

from .types import Candle

_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def generate_candles(
    n: int = 3000,
    *,
    seed: int = 7,
    start_price: float = 100.0,
    timeframe: str = "5m",
    annual_drift: float = 0.0,
    vol: float = 0.004,
    start_ts: int = 1_700_000_000_000,
    regimes: bool = True,
) -> List[Candle]:
    """Generate a deterministic synthetic OHLCV series.

    Not a market model -- just a reproducible price path (optionally with
    alternating up/down/flat regimes) so the engine has something honest
    to chew on in tests. Same seed -> identical candles.
    """
    rng = np.random.default_rng(seed)
    tf_ms = _TF_MS.get(timeframe, 300_000)

    drift = np.zeros(n)
    if regimes:
        block = max(1, n // 6)
        pattern = [vol * 0.6, -vol * 0.6, 0.0, vol * 0.9, -vol * 0.3, 0.0]
        for k in range(n):
            drift[k] = pattern[(k // block) % len(pattern)]
    else:
        drift[:] = annual_drift / (365 * 24 * 60 / (tf_ms / 60_000)) if annual_drift else 0.0

    shocks = rng.normal(0.0, vol, size=n)
    log_returns = drift + shocks
    closes = start_price * np.exp(np.cumsum(log_returns))

    candles: List[Candle] = []
    prev_close = start_price
    for i in range(n):
        close = float(closes[i])
        open_ = float(prev_close)
        hi = max(open_, close) * (1.0 + abs(rng.normal(0.0, vol * 0.5)))
        lo = min(open_, close) * (1.0 - abs(rng.normal(0.0, vol * 0.5)))
        volume = float(abs(rng.normal(1000.0, 200.0)))
        candles.append(Candle(ts=start_ts + i * tf_ms, open=open_, high=hi,
                              low=lo, close=close, volume=volume))
        prev_close = close
    return candles


def load_csv(path: str) -> List[Candle]:
    """Load candles from CSV with headers: ts,open,high,low,close,volume.

    ``ts`` may be epoch seconds or milliseconds (auto-detected).
    """
    candles: List[Candle] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = int(float(row["ts"]))
            if ts < 10_000_000_000:  # looks like seconds
                ts *= 1000
            candles.append(Candle(
                ts=ts, open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
            ))
    candles.sort(key=lambda c: c.ts)
    return candles


def fetch_ohlcv(symbol: str, timeframe: str = "5m", limit: int = 1000,
                exchange_id: str = "binanceusdm") -> List[Candle]:
    """Best-effort fetch via ccxt. Run where the exchange is reachable."""
    import ccxt  # imported lazily so tests don't need ccxt/network

    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return [Candle(ts=int(r[0]), open=float(r[1]), high=float(r[2]),
                   low=float(r[3]), close=float(r[4]), volume=float(r[5]))
            for r in raw]
