import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Callable, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class CandleStore:
    def __init__(self, max_candles: int = 500):
        self.max_candles = max_candles
        # dict[symbol][timeframe] -> deque
        self.data: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.max_candles)))
        self.callbacks: List[Callable] = []
        self._lock = asyncio.Lock()

    def register_callback(self, callback: Callable):
        """Register a callback for when a new candle completes on any timeframe."""
        self.callbacks.append(callback)

    async def add_candle(self, symbol: str, timeframe: str, candle: Candle):
        """Adds a candle and triggers callbacks/resampling if appropriate."""
        async with self._lock:
            store = self.data[symbol][timeframe]
            # Check if this is a new candle or an update to the current one
            if len(store) > 0 and store[-1].timestamp == candle.timestamp:
                store[-1] = candle
            else:
                if len(store) > 0:
                    # Previous candle closed
                    closed_candle = store[-1]
                    for cb in self.callbacks:
                        if asyncio.iscoroutinefunction(cb):
                            asyncio.create_task(cb(symbol, timeframe, closed_candle))
                        else:
                            cb(symbol, timeframe, closed_candle)
                store.append(candle)
                
            if timeframe == '1m':
                await self._resample_from_1m(symbol)

    async def get_candles(self, symbol: str, timeframe: str, count: int = 100) -> List[Candle]:
        async with self._lock:
            store = self.data[symbol][timeframe]
            return list(store)[-count:]

    async def get_latest(self, symbol: str, timeframe: str) -> Optional[Candle]:
        async with self._lock:
            store = self.data[symbol][timeframe]
            if len(store) > 0:
                return store[-1]
            return None

    async def get_dataframe(self, symbol: str, timeframe: str, count: int = 100) -> pd.DataFrame:
        candles = await self.get_candles(symbol, timeframe, count)
        if not candles:
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df = pd.DataFrame([c.__dict__ for c in candles])
        return df

    async def _resample_from_1m(self, symbol: str):
        # resamples 1m to 5m, 15m, 1h, 4h
        # Groups 1m candles. Only emits a new higher-TF candle when the period is complete
        target_tfs = {'5m': 5, '15m': 15, '1h': 60, '4h': 240}
        
        store_1m = self.data[symbol]['1m']
        if not store_1m:
            return

        latest_1m = store_1m[-1]
        ts_1m = latest_1m.timestamp

        for tf, minutes in target_tfs.items():
            # Check if 1m candle closed exactly at the boundary of a higher TF candle
            # This is simplified: assuming timestamp is candle start time.
            # E.g. a 5m candle starting at 10:00 includes 10:00, 10:01, 10:02, 10:03, 10:04.
            # Once we see 10:05 start, the 10:00 5m candle is closed.
            current_tf_ts = ts_1m.replace(second=0, microsecond=0)
            current_tf_ts = current_tf_ts - timedelta(minutes=current_tf_ts.minute % minutes, hours=current_tf_ts.hour % (minutes // 60) if minutes >= 60 else 0)
            
            # Aggregate 1m candles matching this tf_ts
            agg_open = None
            agg_high = float('-inf')
            agg_low = float('inf')
            agg_close = None
            agg_vol = 0.0

            for c in reversed(store_1m):
                c_ts = c.timestamp.replace(second=0, microsecond=0)
                c_tf_ts = c_ts - timedelta(minutes=c_ts.minute % minutes, hours=c_ts.hour % (minutes // 60) if minutes >= 60 else 0)
                
                if c_tf_ts < current_tf_ts:
                    break # older candle
                
                if c_tf_ts == current_tf_ts:
                    if agg_open is None:
                        agg_close = c.close
                    agg_open = c.open # will eventually hold the earliest open
                    agg_high = max(agg_high, c.high)
                    agg_low = min(agg_low, c.low)
                    agg_vol += c.volume
                    
            if agg_open is not None:
                new_candle = Candle(
                    timestamp=current_tf_ts,
                    open=agg_open,
                    high=agg_high,
                    low=agg_low,
                    close=agg_close,
                    volume=agg_vol
                )
                
                # Check if it's the exact same timestamp. 
                tf_store = self.data[symbol][tf]
                if len(tf_store) > 0 and tf_store[-1].timestamp == current_tf_ts:
                    tf_store[-1] = new_candle
                else:
                    if len(tf_store) > 0:
                        # old closed
                        closed_candle = tf_store[-1]
                        for cb in self.callbacks:
                            if asyncio.iscoroutinefunction(cb):
                                asyncio.create_task(cb(symbol, tf, closed_candle))
                            else:
                                cb(symbol, tf, closed_candle)
                    tf_store.append(new_candle)
