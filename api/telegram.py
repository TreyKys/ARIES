import httpx
import logging
from typing import Any
import asyncio

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._lock = asyncio.Lock()
        
    async def _send(self, text: str):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials missing, skipping message")
            return
            
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(self.base_url, json={
                        "chat_id": self.chat_id,
                        "text": text
                    })
                    response.raise_for_status()
            except Exception as e:
                logger.error(f"Failed to send telegram message: {e}")
            await asyncio.sleep(1)

    async def send_signal(self, signal: Any):
        msg = (
            f"🟢 NEW SIGNAL: {getattr(signal, 'direction', 'UNKNOWN')} {getattr(signal, 'symbol', 'UNKNOWN')}\n"
            f"Entry: {getattr(signal, 'price', 0)} | SL: {getattr(signal, 'sl', 0)}\n"
            f"TP1: {getattr(signal, 'tp1', 0)} | TP2: {getattr(signal, 'tp2', 0)}\n"
            f"R:R: {getattr(signal, 'rr', 0)} | Confidence: {getattr(signal, 'confidence', 0)}%\n"
            f"Size: {getattr(signal, 'size', 0)} | Leverage: {getattr(signal, 'leverage', 1)}x"
        )
        await self._send(msg)

    async def send_trade_opened(self, position: Any):
        msg = f"📈 TRADE OPENED: {getattr(position, 'symbol', 'UNKNOWN')} {getattr(position, 'direction', 'UNKNOWN')}"
        await self._send(msg)

    async def send_trade_closed(self, trade: Any):
        pnl = getattr(trade, 'pnl', 0)
        perc = getattr(trade, 'pnl_perc', 0)
        if pnl > 0:
            msg = f"✅ WIN +${pnl} (+{perc}%)"
        else:
            msg = f"❌ LOSS -${abs(pnl)} (-{abs(perc)}%)"
        await self._send(msg)

    async def send_risk_alert(self, risk_tier: str, reason: str):
        await self._send(f"⚠️ RISK TIER: {risk_tier} — {reason}")

    async def send_daily_summary(self, stats: dict):
        await self._send(f"📊 DAILY SUMMARY: {stats}")

    async def send_error(self, error_msg: str):
        await self._send(f"🚨 ENGINE ERROR: {error_msg}")
