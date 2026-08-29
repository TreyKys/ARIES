import asyncio
import logging
from typing import Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class EngineHeartbeat:
    is_running: bool
    mode: str
    risk_tier: str
    timestamp: str

class Engine:
    def __init__(self, settings, database, feed_manager, candle_store, ws_hub, telegram):
        self.settings = settings
        self.database = database
        self.feed_manager = feed_manager
        self.candle_store = candle_store
        self.ws_hub = ws_hub
        self.telegram = telegram
        
        self.mode = getattr(settings, 'MODE', 'MONITOR')
        self.risk_tier = "NORMAL"
        self._running = False
        self._tasks = []
        
        # Placeholders for analyzers
        self.structure_analyzer = lambda *args: None
        self.regime_classifier = lambda *args: "TRENDING"
        self.liquidity_mapper = lambda *args: None
        self.confluence_scorer = lambda *args: 85
        
        self.open_positions = {}

    async def start(self):
        self._running = True
        logger.info(f"ARES-1 ENGINE STARTED — MODE: {self.mode}")
        await self.telegram.send_error(f"ARES-1 online - MODE: {self.mode}")
        
        if hasattr(self.feed_manager, 'start'):
            await self.feed_manager.start()
            
        if hasattr(self.candle_store, 'on_candle_close'):
            self.candle_store.on_candle_close(self._on_candle_close)
            
        self._tasks = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._equity_loop()),
            asyncio.create_task(self._check_halts())
        ]

    async def _on_candle_close(self, symbol, timeframe, candle):
        if timeframe < 15:
            return
            
        logger.debug(f"Candle closed for {symbol} on {timeframe}m")
        confluence = self.confluence_scorer()
        
        if confluence >= 80 and symbol not in self.open_positions:
            signal = type('Signal', (), {
                'symbol': symbol, 'direction': 'LONG', 'price': candle.get('close', 0), 
                'timestamp': datetime.utcnow().isoformat(), 'confidence': confluence
            })()
            
            approved = True
            
            if approved and self.mode != 'MONITOR':
                self.open_positions[symbol] = signal
                await self.telegram.send_trade_opened(signal)
            elif approved and self.mode == 'MONITOR':
                await self.database.log_engine_event("MONITOR_SIGNAL", "Signal generated but not executed", data_json=None)
            else:
                await self.database.log_engine_event("REJECTED_SIGNAL", "Signal rejected by risk gate", data_json=None)
                
            await self.database.save_signal(signal)
            
        await self.ws_hub.broadcast('signal', {"symbol": symbol, "confluence": confluence})

    async def _heartbeat_loop(self):
        while self._running:
            await self.ws_hub.broadcast('heartbeat', self.get_status().__dict__)
            await asyncio.sleep(5)

    async def _equity_loop(self):
        while self._running:
            snapshot = type('EquitySnapshot', (), {'timestamp': datetime.utcnow().isoformat(), 'equity': getattr(self.settings, 'STARTING_CAPITAL', 10000.0), 'available_margin': getattr(self.settings, 'STARTING_CAPITAL', 10000.0)})()
            await self.database.save_equity_snapshot(snapshot)
            await self.ws_hub.broadcast('equity_update', snapshot.__dict__)
            await asyncio.sleep(60)

    async def _check_halts(self):
        while self._running:
            await asyncio.sleep(10)

    async def stop(self):
        self._running = False
        logger.info("Stopping ARES-1 Engine")
        for task in self._tasks:
            task.cancel()
            
        if hasattr(self.feed_manager, 'stop'):
            await self.feed_manager.stop()
            
        await self.database.close()

    def get_status(self) -> EngineHeartbeat:
        return EngineHeartbeat(
            is_running=self._running,
            mode=self.mode,
            risk_tier=self.risk_tier,
            timestamp=datetime.utcnow().isoformat()
        )

    @property
    def is_running(self):
        return self._running
