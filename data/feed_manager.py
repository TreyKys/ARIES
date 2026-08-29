import asyncio
import logging
import httpx
import ccxt.pro as ccxtpro
from datetime import datetime, timezone
from typing import Dict
from .candle_store import CandleStore, Candle
from .sanitizer import DataSanitizer

logger = logging.getLogger(__name__)

class FeedManager:
    def __init__(self, settings: dict, candle_store: CandleStore, sanitizer: DataSanitizer):
        self.settings = settings
        self.candle_store = candle_store
        self.sanitizer = sanitizer
        
        self.exchange = ccxtpro.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        if self.settings.get("MODE") == "PAPER":
            self.exchange.set_sandbox_mode(True)
            
        self.tasks = []
        self.running = False
        
        self.funding_rates: Dict[str, float] = {}
        self.open_interests: Dict[str, float] = {}
        self.order_books: Dict[str, dict] = {}
        self.cvd: Dict[str, float] = {}

    async def start(self):
        self.running = True
        symbols = self.settings.get("SYMBOLS", ["BTC/USDT"])
        oanda_pairs = ["EUR/USD", "GBP/JPY"]
        
        for symbol in symbols:
            if symbol in oanda_pairs:
                self.tasks.append(asyncio.create_task(self._poll_oanda_candles(symbol)))
            else:
                self.tasks.append(asyncio.create_task(self._watch_ohlcv(symbol, '1m')))
                self.tasks.append(asyncio.create_task(self._watch_trades(symbol)))
                self.tasks.append(asyncio.create_task(self._watch_order_book(symbol)))
                self.tasks.append(asyncio.create_task(self._poll_funding_rate(symbol)))
                self.tasks.append(asyncio.create_task(self._poll_open_interest(symbol)))
                
        logger.info("FeedManager started.")

    async def stop(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await self.exchange.close()
        logger.info("FeedManager stopped.")

    async def _watch_ohlcv(self, symbol: str, timeframe: str):
        delay = 1
        while self.running:
            try:
                candles = await self.exchange.watch_ohlcv(symbol, timeframe)
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
                    candle = self.sanitizer.clean_candle(candle)
                    is_valid, msg = self.sanitizer.validate_candle(candle, symbol)
                    if is_valid:
                        await self.candle_store.add_candle(symbol, timeframe, candle)
                delay = 1
            except Exception as e:
                logger.error(f"Error watching OHLCV for {symbol}: {e}")
                await asyncio.sleep(delay)
                delay = min(60, delay * 2)

    async def _watch_trades(self, symbol: str):
        delay = 1
        self.cvd[symbol] = 0.0
        while self.running:
            try:
                trades = await self.exchange.watch_trades(symbol)
                for trade in trades:
                    side = trade.get('side', '')
                    amount = trade.get('amount', 0.0)
                    if side == 'buy':
                        self.cvd[symbol] += amount
                    elif side == 'sell':
                        self.cvd[symbol] -= amount
                delay = 1
            except Exception as e:
                logger.error(f"Error watching trades for {symbol}: {e}")
                await asyncio.sleep(delay)
                delay = min(60, delay * 2)

    async def _watch_order_book(self, symbol: str):
        delay = 1
        while self.running:
            try:
                ob = await self.exchange.watch_order_book(symbol, limit=20)
                self.order_books[symbol] = ob
                delay = 1
            except Exception as e:
                logger.error(f"Error watching order book for {symbol}: {e}")
                await asyncio.sleep(delay)
                delay = min(60, delay * 2)

    async def _poll_funding_rate(self, symbol: str):
        while self.running:
            try:
                funding = await self.exchange.fetch_funding_rate(symbol)
                self.funding_rates[symbol] = funding.get('fundingRate', 0.0)
            except Exception as e:
                logger.error(f"Error polling funding rate for {symbol}: {e}")
            await asyncio.sleep(30)

    async def _poll_open_interest(self, symbol: str):
        while self.running:
            try:
                oi = await self.exchange.fetch_open_interest(symbol)
                self.open_interests[symbol] = oi.get('openInterestValue', 0.0)
            except Exception as e:
                logger.error(f"Error polling open interest for {symbol}: {e}")
            await asyncio.sleep(30)

    async def _poll_oanda_candles(self, symbol: str):
        # Poll OANDA REST API v20 every 5 seconds for '1m' candles
        pair = symbol.replace("/", "_")
        url = f"https://api-fxtrade.oanda.com/v3/instruments/{pair}/candles"
        # Mock polling logic since we need auth for real OANDA
        # Assuming token is in settings for real usage
        token = self.settings.get("OANDA_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}"}
        
        while self.running:
            try:
                async with httpx.AsyncClient() as client:
                    params = {"granularity": "M1", "count": 2, "price": "M"}
                    resp = await client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for c in data.get("candles", []):
                            if c.get("complete", False):
                                ts = datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
                                mid = c["mid"]
                                candle = Candle(
                                    timestamp=ts,
                                    open=float(mid["o"]),
                                    high=float(mid["h"]),
                                    low=float(mid["l"]),
                                    close=float(mid["c"]),
                                    volume=float(c.get("volume", 0))
                                )
                                candle = self.sanitizer.clean_candle(candle)
                                if self.sanitizer.validate_candle(candle, symbol)[0]:
                                    await self.candle_store.add_candle(symbol, "1m", candle)
            except Exception as e:
                logger.error(f"Error polling OANDA for {symbol}: {e}")
            await asyncio.sleep(5)

    def get_funding_rate(self, symbol: str) -> float:
        return self.funding_rates.get(symbol, 0.0)

    def get_open_interest(self, symbol: str) -> float:
        return self.open_interests.get(symbol, 0.0)

    def get_order_book(self, symbol: str) -> dict:
        return self.order_books.get(symbol, {})

    def get_cvd(self, symbol: str) -> float:
        return self.cvd.get(symbol, 0.0)
