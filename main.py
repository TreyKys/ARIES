import asyncio
import logging
import os
from dotenv import load_dotenv

from config.settings import get_settings
from config.pairs import WATCHED_PAIRS
from storage.database import Database
from api.supabase_client import SupabaseManager
from api.telegram import TelegramNotifier
from core.engine import Engine
from data.feed_manager import FeedManager
from data.candle_store import CandleStore
from data.sanitizer import DataSanitizer

async def main():
    load_dotenv()
    settings = get_settings()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    logger = logging.getLogger('ares1')
    logger.info('═' * 60)
    logger.info('  ARES-1 AUTONOMOUS TRADING ENGINE (SUPABASE REALTIME)')
    logger.info('═' * 60)
    
    database = Database()
    await database.init()
    
    # Supabase replaces WebSocketHub
    sb_url = os.getenv('SUPABASE_URL', '')
    sb_key = os.getenv('SUPABASE_KEY', '')
    supabase_manager = SupabaseManager(sb_url, sb_key)
    
    telegram = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    
    candle_store = CandleStore(max_candles=500)
    sanitizer = DataSanitizer()
    feed_manager = FeedManager(settings, candle_store, sanitizer)
    
    # Pass supabase_manager where ws_hub used to go
    engine = Engine(settings, database, feed_manager, candle_store, supabase_manager, telegram)
    
    # We no longer run the FastAPI Uvicorn server! Supabase handles the frontend!
    try:
        await engine.start()
        # Keep engine running forever
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await engine.stop()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
