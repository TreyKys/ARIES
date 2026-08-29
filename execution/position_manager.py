import logging
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Callable
import time

logger = logging.getLogger(__name__)

@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    size: float
    stop_loss: float
    tp1: float
    tp2: float
    order_id: str
    leverage: int
    unrealized_pnl: float = 0.0
    mfe: float = 0.0  # Maximum Favorable Excursion
    mae: float = 0.0  # Maximum Adverse Excursion
    status: str = 'open' # 'open', 'partial', 'closed', 'pending'

class PositionManager:
    def __init__(self, executor: Any, risk_manager: Any, settings: Any):
        self.executor = executor
        self.risk_manager = risk_manager
        self.settings = settings
        self.positions: Dict[str, Position] = {}
        
        self.on_position_update_callbacks: List[Callable] = []
        self.on_position_close_callbacks: List[Callable] = []

    def on_position_update(self, callback: Callable):
        self.on_position_update_callbacks.append(callback)

    def on_position_close(self, callback: Callable):
        self.on_position_close_callbacks.append(callback)
        
    async def _emit_update(self, position: Position):
        for cb in self.on_position_update_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(position)
                else:
                    cb(position)
            except Exception as e:
                logger.error(f"Error in on_position_update callback: {e}")

    async def _emit_close(self, position: Position, reason: str, pnl: float, r_multiple: float):
        for cb in self.on_position_close_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(position, reason, pnl, r_multiple)
                else:
                    cb(position, reason, pnl, r_multiple)
            except Exception as e:
                logger.error(f"Error in on_position_close callback: {e}")

    async def open_position(self, signal: Any) -> Optional[Position]:
        """Opens a new position based on a signal."""
        leverage = getattr(self.settings, 'DEFAULT_LEVERAGE', 1)
        
        # 1. Set leverage and margin mode
        await self.executor.set_leverage(signal.symbol, leverage)
        await self.executor.set_margin_mode(signal.symbol, 'isolated')
        
        # 2. Place limit order at signal.entry_price
        order = await self.executor.place_limit_order(
            signal.symbol, 
            signal.side, 
            signal.size, 
            signal.entry_price
        )
        
        if not order:
            logger.error("Failed to open position: order placement failed.")
            return None
            
        order_id = order.get('id', 'mock_id')
            
        # 3. Create Position object
        pos = Position(
            symbol=signal.symbol,
            side=signal.side,
            entry_price=signal.entry_price,
            size=signal.size,
            stop_loss=signal.stop_loss,
            tp1=signal.tp1,
            tp2=signal.tp2,
            order_id=order_id,
            leverage=leverage,
            status='pending'
        )
        
        self.positions[signal.symbol] = pos
        logger.info(f"POSITION OPENED: {pos.side} {pos.symbol} @ {pos.entry_price} | SL: {pos.stop_loss} | TP1: {pos.tp1} | TP2: {pos.tp2}")
        
        # Start fill monitoring task
        asyncio.create_task(self.check_fill_timeout(pos))
        asyncio.create_task(self.monitor_position(pos))
        
        await self._emit_update(pos)
        
        return pos

    async def monitor_position(self, position: Position):
        """Continuously monitors an open position."""
        while position.status in ['open', 'partial', 'pending']:
            try:
                # Fetch current price via exchange orderbook/ticker or websocket in a real app
                # For this implementation we will mock it if not available, or fetch ticker
                ticker = await self.executor.exchange.fetch_ticker(position.symbol)
                current_price = ticker['last']
                
                if position.status == 'pending':
                    # Check if filled
                    order_status = await self.executor.get_order_status(position.order_id, position.symbol)
                    if order_status and order_status.get('status') == 'closed':
                        position.status = 'open'
                        await self._emit_update(position)
                    else:
                        await asyncio.sleep(1)
                        continue
                        
                # Update PnL, MFE, MAE
                if position.side.upper() == 'LONG':
                    pnl = (current_price - position.entry_price) * position.size
                    position.mfe = max(position.mfe, current_price)
                    position.mae = min(position.mae, current_price)
                else:
                    pnl = (position.entry_price - current_price) * position.size
                    position.mfe = min(position.mfe, current_price)
                    position.mae = max(position.mae, current_price)
                    
                position.unrealized_pnl = pnl
                
                # Check TP1 hit
                if position.status == 'open':
                    if (position.side.upper() == 'LONG' and current_price >= position.tp1) or \
                       (position.side.upper() == 'SHORT' and current_price <= position.tp1):
                        logger.info(f"TP1 hit for {position.symbol}. Partial close 50%.")
                        await self.partial_close(position, 0.5)
                        
                        # Move SL to breakeven + fees (approximate)
                        fee_offset = position.entry_price * 0.001
                        new_sl = position.entry_price + fee_offset if position.side.upper() == 'LONG' else position.entry_price - fee_offset
                        await self.update_stop_loss(position, new_sl)
                        
                # Check TP2 / Trailing Stop logic
                # For brevity, implementing a basic SL hit check
                if (position.side.upper() == 'LONG' and current_price <= position.stop_loss) or \
                   (position.side.upper() == 'SHORT' and current_price >= position.stop_loss):
                    logger.info(f"SL hit for {position.symbol}.")
                    await self.close_position(position, "SL_HIT")
                    break

                # Additional Trailing Stop logic can be added here
                # Check TP2 zone -> activate trailing stop (1.5x ATR below price)
                # ...
                
                await self._emit_update(position)
                
            except Exception as e:
                logger.error(f"Error monitoring position {position.symbol}: {e}")
                
            await asyncio.sleep(1)

    async def partial_close(self, position: Position, pct: float = 0.5):
        """Closes a percentage of the position."""
        close_amount = position.size * pct
        side_to_close = 'SELL' if position.side.upper() == 'LONG' else 'BUY'
        
        order = await self.executor.place_market_order(position.symbol, side_to_close, close_amount)
        if order:
            position.size -= close_amount
            position.status = 'partial'
            await self._emit_update(position)
            logger.info(f"PARTIAL CLOSE successful: {close_amount} {position.symbol}")

    async def close_position(self, position: Position, reason: str):
        """Fully closes a position."""
        side_to_close = 'SELL' if position.side.upper() == 'LONG' else 'BUY'
        
        order = await self.executor.place_market_order(position.symbol, side_to_close, position.size)
        
        # Calculate final PnL and R-multiple
        # Simplified calculation
        pnl = position.unrealized_pnl
        risk = abs(position.entry_price - position.stop_loss) * position.size
        r_multiple = pnl / risk if risk > 0 else 0
        
        position.status = 'closed'
        position.size = 0
        
        if position.symbol in self.positions:
            del self.positions[position.symbol]
            
        await self._emit_close(position, reason, pnl, r_multiple)
        logger.info(f"POSITION CLOSED: {position.symbol} | Reason: {reason} | PnL: {pnl} | R-Multiple: {r_multiple}")

    async def check_fill_timeout(self, position: Position, timeout: int = 900):
        """Cancels order if not filled within timeout."""
        await asyncio.sleep(timeout)
        if position.status == 'pending':
            logger.info(f"Order fill timeout for {position.symbol}. Cancelling order.")
            await self.executor.cancel_order(position.order_id, position.symbol)
            position.status = 'closed'
            if position.symbol in self.positions:
                del self.positions[position.symbol]
            await self._emit_update(position)

    def get_open_positions(self) -> List[Position]:
        return list(self.positions.values())

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.positions

    async def update_stop_loss(self, position: Position, new_sl: float):
        position.stop_loss = new_sl
        logger.info(f"Updated SL for {position.symbol} to {new_sl}")
        await self._emit_update(position)
