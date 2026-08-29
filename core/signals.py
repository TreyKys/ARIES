import logging
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SignalAction(str, Enum):
    BUY_LONG = "BUY_LONG"
    SELL_SHORT = "SELL_SHORT"
    HOLD = "HOLD"

class Signal(BaseModel):
    symbol: str
    action: SignalAction
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    position_size: float
    confidence_score: float
    metadata: dict

class SignalGenerator:
    def __init__(self):
        pass

    def generate(self, 
                 symbol: str, 
                 candle_store: Any, 
                 structure_data: Any, 
                 regime: Any, 
                 liquidity: Any, 
                 confluence: Any, 
                 account_state: dict, 
                 settings: dict) -> Optional[Signal]:
        """
        Generate trade signal based on gathered analysis.
        Returns None (abstains) if conditions aren't met.
        """
        try:
            # We expect 'confluence' here to be an instance of ConfluenceResult or a dict to pass to scorer.
            # Assuming a ConfluenceResult is already calculated, or we just rely on its output.
            
            if not getattr(confluence, 'is_tradeable', False):
                logger.info(f"Signal suppressed for {symbol} due to insufficient confluence.")
                return None
                
            score = getattr(confluence, 'total_score', 0)
            confidence = score / 100.0
            
            # Determine direction from structure/confluence analysis
            # We assume metadata holds the analyzed intent
            direction_intent = account_state.get('analyzed_direction', 'HOLD')
            
            if direction_intent == 'LONG':
                action = SignalAction.BUY_LONG
            elif direction_intent == 'SHORT':
                action = SignalAction.SELL_SHORT
            else:
                return None
                
            # Derive prices (mockup logic mirroring requirements)
            current_price = account_state.get('current_price', 0.0)
            atr = account_state.get('atr', 0.0)
            
            # Entry logic
            ob_high = account_state.get('ob_high', current_price)
            ob_low = account_state.get('ob_low', current_price)
            
            if action == SignalAction.BUY_LONG:
                entry_price = ob_high
                stop_loss = ob_low - (1.5 * atr)
                risk = entry_price - stop_loss
                take_profit_1 = entry_price + (2 * risk)
                take_profit_2 = liquidity.bsl_levels[0] if getattr(liquidity, 'bsl_levels', []) else take_profit_1 * 1.05
            else:
                entry_price = ob_low
                stop_loss = ob_high + (1.5 * atr)
                risk = stop_loss - entry_price
                take_profit_1 = entry_price - (2 * risk)
                take_profit_2 = liquidity.ssl_levels[-1] if getattr(liquidity, 'ssl_levels', []) else take_profit_1 * 0.95
                
            # Position sizing mock
            risk_pct = settings.get('risk_per_trade', 0.01)
            balance = account_state.get('balance', 1000.0)
            risk_amount = balance * risk_pct
            
            position_size = risk_amount / risk if risk > 0 else 0.0
            
            signal = Signal(
                symbol=symbol,
                action=action,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
                position_size=position_size,
                confidence_score=confidence,
                metadata={"confluence_score": score}
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None
