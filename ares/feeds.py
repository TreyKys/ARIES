"""Market data feeds for the live engine.

- ``replay_candles``: yield candles from a CSV as fast as possible
  (deterministic dry-run; also lets a geo-blocked host verify the engine).
- ``ccxt_live_feed``: poll a real exchange for newly *closed* candles and
  dispatch them. Run this where the exchange API is reachable.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Iterable, Iterator, List

from . import datasource
from .types import Candle


def replay_candles(csv_path: str) -> Iterator[Candle]:
    yield from datasource.load_csv(csv_path)


async def ccxt_live_feed(
    symbols: List[str],
    timeframe: str,
    on_candle: Callable[[str, Candle], Awaitable[None]],
    *,
    exchange_id: str = "binanceusdm",
    poll_seconds: int = 10,
) -> None:
    import ccxt.async_support as ccxt  # lazy: only needed for live

    exchange = getattr(ccxt, exchange_id)({
        "enableRateLimit": True, "options": {"defaultType": "future"},
    })
    last_ts = {s: None for s in symbols}
    try:
        while True:
            for s in symbols:
                try:
                    raw = await exchange.fetch_ohlcv(s, timeframe, limit=2)
                except Exception as e:  # noqa: BLE001
                    # Binance geo-blocks many cloud IPs (HTTP 451). Surface it.
                    print(f"[feed] {s}: fetch failed: {str(e)[:120]}")
                    continue
                if len(raw) >= 2:
                    c = raw[-2]  # -1 is the still-forming candle; -2 just closed
                    ts = int(c[0])
                    if last_ts[s] != ts:
                        last_ts[s] = ts
                        await on_candle(s, Candle(ts, float(c[1]), float(c[2]),
                                                  float(c[3]), float(c[4]), float(c[5])))
            await asyncio.sleep(poll_seconds)
    finally:
        await exchange.close()
