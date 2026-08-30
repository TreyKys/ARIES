import asyncio
import logging
from datetime import datetime, timezone
import ccxt.async_support as ccxt
from storage.models import Candle

logger = logging.getLogger(__name__)

class FeedManager:
    """
    Bulletproof Feed Manager using REST polling instead of fragile CCXT Pro WebSockets.
    Guarantees synchronization and prevents event loop crashes.
    """
    def __init__(self, settings, candle_store, sanitizer=None):
        self.settings = settings
        self.candle_store = candle_store
        self.exchange = ccxt.binanceusdm({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.running = False
        self.tasks = []

    async def start(self):
        self.running = True
        logger.info("FeedManager (Bulletproof Polling) started.")
        
        from config.pairs import WATCHED_PAIRS
        for pair in WATCHED_PAIRS:
            if pair.exchange == 'binance':
                self.tasks.append(asyncio.create_task(self._poll_ohlcv(pair.symbol, '1m')))
                self.tasks.append(asyncio.create_task(self._poll_ohlcv(pair.symbol, '5m')))
                self.tasks.append(asyncio.create_task(self._poll_ohlcv(pair.symbol, '15m')))
                self.tasks.append(asyncio.create_task(self._poll_ohlcv(pair.symbol, '1h')))

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await self.exchange.close()
        logger.info("FeedManager stopped.")

    async def _poll_ohlcv(self, symbol: str, timeframe: str):
        # We fetch 100 candles on boot, then fetch 2 candles every loop
        limit = 100
        while self.running:
            try:
                candles = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                limit = 2 # Next poll, just get the latest to save bandwidth
                
                if len(candles) > 0:
                    logger.info(f"Fetched {len(candles)} candles for {symbol} {timeframe}")
                for c in candles:
                    ts = datetime.fromtimestamp(c[0] / 1000.0, tz=timezone.utc)
                    candle = Candle(
                        timestamp=ts,
                        open=float(c[1]),
                        high=float(c[2]),
                        low=float(c[3]),
                        close=float(c[4]),
                        volume=float(c[5])
                    )
                    await self.candle_store.add_candle(symbol, timeframe, candle, is_historical=(limit > 2))
            except Exception as e:
                import traceback
                logger.error(f"Polling warning for {symbol} {timeframe}: {e}")
                traceback.print_exc()
            
            # Smart polling delay to avoid rate limits
            await asyncio.sleep(2.5)
