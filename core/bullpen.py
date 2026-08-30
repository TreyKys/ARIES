import numpy as np
import pandas as pd

class Bullpen:
    """
    The 17 Grunt Workers performing raw TA and metric crunching.
    """
    def __init__(self, settings, candle_store):
        self.settings = settings
        self.candle_store = candle_store

    async def analyze(self, symbol: str) -> dict:
        """
        Runs all grunt workers and returns a unified state dictionary.
        """
        # Fetch data
        df_1m = await self.candle_store.get_dataframe(symbol, '1m')
        df_5m = await self.candle_store.get_dataframe(symbol, '5m')
        df_15m = await self.candle_store.get_dataframe(symbol, '15m')
        df_1h = await self.candle_store.get_dataframe(symbol, '1h')
        
        if df_1m.empty or df_1h.empty:
            return {'ready': False}

        close_1m = df_1m['close'].iloc[-1]
        
        # 1. Trend Workers
        ema_1h = df_1h['close'].ewm(span=20).mean().iloc[-1]
        macro_trend = "BULLISH" if close_1m > ema_1h else "BEARISH"
        
        ema_15m = df_15m['close'].ewm(span=20).mean().iloc[-1]
        structure_15m = "BULLISH" if close_1m > ema_15m else "BEARISH"
        
        # 2. Mean Reversion Workers (RSI)
        delta = df_5m['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_5m = 100 - (100 / (1 + rs)).iloc[-1]
        
        # 3. Volatility / ATR Worker
        high_low = df_1m['high'] - df_1m['low']
        high_close = np.abs(df_1m['high'] - df_1m['close'].shift())
        low_close = np.abs(df_1m['low'] - df_1m['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr_1m = true_range.rolling(14).mean().iloc[-1]
        
        # 4. Regime Worker (Asian vs NY)
        import datetime
        current_hour = datetime.datetime.utcnow().hour
        if 23 <= current_hour or current_hour < 8:
            regime = "ASIAN_RANGE"
        elif 12 <= current_hour < 16:
            regime = "NY_OVERLAP"
        else:
            regime = "CHOP"
            
        # 5. Cost Gatekeeper Worker
        # Simulated spread for micro accounts
        spread = close_1m * 0.0002 # 2 bps spread
        commission = close_1m * 0.0004 # 4 bps commission
        total_cost = spread + commission
        
        # 6. Retail Sentiment Worker (Simulated for now)
        # Randomly generate retail sentiment, biased towards mean 0.5
        retail_long_ratio = np.clip(np.random.normal(0.5, 0.15), 0, 1)

        return {
            'ready': True,
            'symbol': symbol,
            'current_price': close_1m,
            'macro_trend': macro_trend,
            'structure_15m': structure_15m,
            'rsi_5m': rsi_5m,
            'atr_1m': atr_1m,
            'regime': regime,
            'total_cost': total_cost,
            'retail_long_ratio': retail_long_ratio
        }
