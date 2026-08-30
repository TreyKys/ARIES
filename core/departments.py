import datetime
import logging
import traceback

logger = logging.getLogger(__name__)

class HistorianDepartment:
    """
    RAG Vector Memory. Queries Supabase pgvector to find the historical win rate
    of the exact mathematical market structure we are currently seeing.
    """
    def __init__(self, supabase):
        self.supabase = supabase

    def get_historical_precedent(self, state: dict) -> dict:
        try:
            # We construct a 10-D vector representing the market structure
            # Normalizing values to [-1, 1] for cosine similarity
            vector = [
                1.0 if state.get('macro_trend') == 'BULLISH' else -1.0,
                1.0 if state.get('structure_15m') == 'BULLISH' else -1.0,
                (state.get('rsi_5m', 50) - 50) / 50.0,
                min(state.get('atr_1m', 0.0) / 100.0, 1.0),
                state.get('retail_long_ratio', 0.5) * 2 - 1.0,
                0.0, 0.0, 0.0, 0.0, 0.0 # Padding for 10D
            ]
            
            # Query Supabase RPC
            res = self.supabase.client.rpc('match_trades', {
                'query_embedding': vector,
                'match_threshold': 0.85,
                'match_count': 10
            }).execute()
            
            matches = res.data or []
            if not matches:
                return {'has_precedent': False, 'win_rate': 0.0, 'matches': 0}
                
            wins = sum(1 for m in matches if m.get('pnl_usd', 0) > 0)
            win_rate = (wins / len(matches)) * 100
            
            return {
                'has_precedent': True,
                'win_rate': win_rate,
                'matches': len(matches)
            }
        except Exception as e:
            logger.debug(f"Historian Error (table/rpc might be missing): {e}")
            return {'has_precedent': False, 'win_rate': 0.0, 'matches': 0}

class MacroDesk:
    """
    Monitors economic schedules and enforces the "News Shield".
    """
    def check_macro_shield(self) -> dict:
        now = datetime.datetime.utcnow()
        # High impact news typically at 12:30 UTC or 13:30 UTC (CPI/NFP) and 18:00 UTC (FOMC)
        is_shield_active = False
        reason = ""
        
        # Example hardcoded shield logic (in production, polls an API)
        if now.hour == 13 and 15 <= now.minute <= 45:
            is_shield_active = True
            reason = "Pre/Post US Data Release Window"
        elif now.hour == 18 and 0 <= now.minute <= 30:
            is_shield_active = True
            reason = "FOMC Volatility Window"
            
        return {'is_shield_active': is_shield_active, 'reason': reason}

class OrderFlowDepartment:
    """
    Analyzes depth of market (Order Book) to find liquidity sweeps and retail traps.
    """
    def __init__(self, feed_manager):
        self.feed_manager = feed_manager

    async def get_liquidity_imbalance(self, symbol: str) -> dict:
        try:
            orderbook = await self.feed_manager.exchange.fetch_order_book(symbol, limit=20)
            bids = sum(bid[1] for bid in orderbook['bids'])
            asks = sum(ask[1] for ask in orderbook['asks'])
            
            total = bids + asks
            if total == 0:
                return {'imbalance': 0, 'bias': 'NEUTRAL'}
                
            bid_ratio = bids / total
            
            # If bids are heavily stacked, price might sweep down to collect them.
            if bid_ratio > 0.65:
                bias = "BEARISH_SWEEP" # Huge buy walls often act as magnets for sweeps
            elif bid_ratio < 0.35:
                bias = "BULLISH_SWEEP"
            else:
                bias = "NEUTRAL"
                
            return {
                'imbalance': round(bid_ratio, 2),
                'bias': bias
            }
        except Exception as e:
            logger.debug(f"OrderFlow Error: {e}")
            return {'imbalance': 0.5, 'bias': 'NEUTRAL'}
