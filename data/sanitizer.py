import logging
import statistics
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Tuple
from .candle_store import Candle

logger = logging.getLogger(__name__)

class DataSanitizer:
    def __init__(self):
        self.rolling_prices = defaultdict(lambda: deque(maxlen=20))
    
    def validate_candle(self, candle: Candle, symbol: str) -> Tuple[bool, str]:
        if not (candle.high >= candle.open and candle.high >= candle.close):
            return False, "High must be >= Open and Close"
        if not (candle.low <= candle.open and candle.low <= candle.close):
            return False, "Low must be <= Open and Close"
        if candle.volume < 0:
            return False, "Volume cannot be negative"
        
        now = datetime.now(timezone.utc)
        candle_ts = candle.timestamp
        if candle_ts.tzinfo is None:
            candle_ts = candle_ts.replace(tzinfo=timezone.utc)
            
        if candle_ts > now:
            return False, "Timestamp is in the future"
            
        if any(p <= 0 for p in [candle.open, candle.high, candle.low, candle.close]):
            return False, "Prices must be positive and non-zero"
            
        return True, ""

    def detect_outlier(self, price: float, symbol: str) -> bool:
        prices = self.rolling_prices[symbol]
        
        if len(prices) < 20:
            prices.append(price)
            return False
            
        median = statistics.median(prices)
        stdev = statistics.stdev(prices)
        
        prices.append(price)
        
        if stdev == 0:
            return False
            
        if abs(price - median) > 3 * stdev:
            return True
            
        return False

    def detect_fat_finger(self, tick_price: float, last_price: float, atr: float) -> bool:
        if atr <= 0:
            return False
        if abs(tick_price - last_price) > 4 * atr:
            return True
        return False

    def clean_candle(self, candle: Candle) -> Candle:
        clamped_high = max(candle.high, candle.open, candle.close)
        clamped_low = min(candle.low, candle.open, candle.close)
        clamped_vol = max(0.0, candle.volume)
        
        return Candle(
            timestamp=candle.timestamp,
            open=candle.open,
            high=clamped_high,
            low=clamped_low,
            close=candle.close,
            volume=clamped_vol
        )
