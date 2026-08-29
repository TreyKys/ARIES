import logging
from typing import Dict, Any, Optional, List
import ccxt.pro

logger = logging.getLogger(__name__)

class OrderExecutor:
    def __init__(self, settings: Any):
        self.settings = settings
        self.mode = getattr(settings, 'MODE', 'PAPER')
        
        exchange_class = getattr(ccxt.pro, getattr(settings, 'EXCHANGE', 'binance'))
        self.exchange = exchange_class({
            'apiKey': getattr(settings, 'API_KEY', ''),
            'secret': getattr(settings, 'API_SECRET', ''),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        if self.mode == 'PAPER':
            self.exchange.set_sandbox_mode(True)
            logger.info("Executor initialized in PAPER mode (testnet)")
        elif self.mode == 'LIVE':
            self.exchange.set_sandbox_mode(False)
            logger.warning("Executor initialized in LIVE mode (real money)")
        elif self.mode == 'MONITOR':
            logger.info("Executor initialized in MONITOR mode (no execution)")

    async def connect(self):
        """Initializes exchange connection and loads markets."""
        if self.mode != 'MONITOR':
            try:
                await self.exchange.load_markets()
                logger.info("Exchange markets loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load markets: {e}")

    async def close(self):
        """Closes exchange connection."""
        if self.mode != 'MONITOR':
            try:
                await self.exchange.close()
                logger.info("Exchange connection closed.")
            except Exception as e:
                logger.error(f"Failed to close connection: {e}")

    async def place_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Optional[Dict]:
        """Places a limit order."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD PLACE LIMIT ORDER: {side} {amount} {symbol} @ {price}")
            return None
            
        try:
            logger.info(f"LIMIT ORDER PLACED: {side} {amount} {symbol} @ {price}")
            order = await self.exchange.create_limit_order(symbol, side, amount, price)
            return order
        except Exception as e:
            logger.error(f"Failed to place limit order: {e}")
            return None

    async def place_market_order(self, symbol: str, side: str, amount: float) -> Optional[Dict]:
        """Places a market order."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD PLACE MARKET ORDER: {side} {amount} {symbol}")
            return None
            
        try:
            logger.info(f"MARKET ORDER PLACED: {side} {amount} {symbol}")
            order = await self.exchange.create_market_order(symbol, side, amount)
            return order
        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return None

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancels an open order."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD CANCEL ORDER: {order_id} on {symbol}")
            return True
            
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"CANCELLED ORDER: {order_id} on {symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def modify_order(self, order_id: str, symbol: str, amount: Optional[float] = None, price: Optional[float] = None) -> Optional[Dict]:
        """Modifies an open order."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD MODIFY ORDER: {order_id} on {symbol} - new amount: {amount}, new price: {price}")
            return None
            
        try:
            order = await self.exchange.edit_order(order_id, symbol, 'limit', None, amount, price)
            logger.info(f"MODIFIED ORDER: {order_id} on {symbol}")
            return order
        except Exception as e:
            logger.error(f"Failed to modify order {order_id}: {e}")
            return None

    async def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """Gets the status of an order."""
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.error(f"Failed to fetch order status for {order_id}: {e}")
            return None

    async def get_balance(self) -> Optional[Dict]:
        """Gets account balance."""
        try:
            balance = await self.exchange.fetch_balance()
            # Extract total, free, used assuming USDT for simplicity
            usdt_bal = balance.get('USDT', {})
            return {
                'total': usdt_bal.get('total', 0.0),
                'free': usdt_bal.get('free', 0.0),
                'used': usdt_bal.get('used', 0.0)
            }
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return None

    async def get_positions(self) -> List[Dict]:
        """Gets list of open positions."""
        try:
            positions = await self.exchange.fetch_positions()
            # Filter for open positions
            return [p for p in positions if float(p.get('contracts', 0)) > 0]
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Sets leverage for a symbol."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD SET LEVERAGE: {leverage}x on {symbol}")
            return True
            
        try:
            await self.exchange.set_leverage(leverage, symbol)
            logger.info(f"SET LEVERAGE: {leverage}x on {symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage on {symbol}: {e}")
            return False

    async def set_margin_mode(self, symbol: str, mode: str = 'isolated') -> bool:
        """Sets margin mode for a symbol."""
        if self.mode == 'MONITOR':
            logger.info(f"WOULD SET MARGIN MODE: {mode} on {symbol}")
            return True
            
        try:
            await self.exchange.set_margin_mode(mode, symbol)
            logger.info(f"SET MARGIN MODE: {mode} on {symbol}")
            return True
        except Exception as e:
            logger.error(f"Failed to set margin mode on {symbol}: {e}")
            return False
