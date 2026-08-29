import asyncio
import logging
import uvicorn
from types import SimpleNamespace

from storage.database import Database
from api.server import create_app
from api.ws_hub import WebSocketHub
from api.telegram import TelegramNotifier
from core.engine import Engine

class MockFeedManager:
    async def start(self): pass
    async def stop(self): pass

class MockCandleStore:
    def on_candle_close(self, cb): pass

class MockDataSanitizer:
    pass

WATCHED_PAIRS = [SimpleNamespace(symbol='BTC/USDT')]

def get_settings():
    return SimpleNamespace(
        MODE='PAPER',
        STARTING_CAPITAL=10000,
        API_HOST='0.0.0.0',
        API_PORT=8000,
        TELEGRAM_BOT_TOKEN='',
        TELEGRAM_CHAT_ID=''
    )

async def main():
    settings = get_settings()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    logger = logging.getLogger('ares1')
    logger.info('═' * 60)
    logger.info('  ARES-1 AUTONOMOUS TRADING ENGINE')
    logger.info(f'  Mode: {settings.MODE}')
    logger.info(f'  Capital: ${settings.STARTING_CAPITAL}')
    logger.info(f'  Pairs: {", ".join(p.symbol for p in WATCHED_PAIRS)}')
    logger.info('═' * 60)
    
    database = Database()
    await database.init()
    
    candle_store = MockCandleStore()
    sanitizer = MockDataSanitizer()
    feed_manager = MockFeedManager()
    ws_hub = WebSocketHub()
    telegram = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    
    engine = Engine(settings, database, feed_manager, candle_store, ws_hub, telegram)
    
    app = create_app(engine, ws_hub, database)
    
    config = uvicorn.Config(app, host=settings.API_HOST, port=settings.API_PORT, log_level='info')
    server = uvicorn.Server(config)
    
    try:
        await asyncio.gather(
            engine.start(),
            server.serve()
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await engine.stop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
