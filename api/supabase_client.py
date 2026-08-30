import os
import logging
from supabase import create_client, Client

logger = logging.getLogger('ares1')

class SupabaseManager:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    async def broadcast(self, topic: str, data: dict):
        # We don't use raw WebSockets anymore, we use Supabase Tables as the message broker.
        try:
            if topic == 'heartbeat':
                pass # Optionally write to system_state for uptime, but usually not needed as frequently
            elif topic == 'equity_update':
                # Write to the system_state table
                self.client.table('system_state').update({
                    'balance': data.get('equity', 50.0),
                    'today_pnl_abs': data.get('pnl_abs', 0.0),
                    'today_pnl_pct': data.get('pnl_pct', 0.0),
                    'win_rate': 0, # Will calculate later
                    'is_connected': True
                }).eq('id', 1).execute()
            elif topic == 'signal':
                # Write to signals table
                self.client.table('signals').insert({
                    'symbol': data.get('symbol', 'UNKNOWN'),
                    'action': data.get('direction', 'LONG'),
                    'confidence': data.get('confluence', 0.0),
                    'risk_tier': 'NORMAL'
                }).execute()
        except Exception as e:
            logger.error(f"Supabase broadcast error: {e}")
