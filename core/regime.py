import logging
from enum import Enum
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

class MarketRegime(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    VOLATILE_BREAKOUT = "VOLATILE_BREAKOUT"
    UNKNOWN = "UNKNOWN"

class RegimeClassifier:
    def __init__(self):
        pass

    def classify(self, df_4h: pd.DataFrame, df_1h: pd.DataFrame) -> MarketRegime:
        """Classify market regime based on 4h and 1h indicators."""
        try:
            # We assume compute_all has been called on these dataframes, providing ema50, ema200, adx, atr, bb_width
            if len(df_4h) < 1:
                return MarketRegime.UNKNOWN
                
            last_4h = df_4h.iloc[-1]
            price = last_4h['close']
            
            ema50 = last_4h.get('ema50', price)
            ema200 = last_4h.get('ema200', price)
            adx = last_4h.get('adx', 0)
            atr = last_4h.get('atr', 0)
            bb_width = last_4h.get('bb_width', 0)
            
            # Historical means for breakout detection
            avg_bb_width = df_4h['bb_width'].rolling(20).mean().iloc[-1] if 'bb_width' in df_4h else 1
            avg_atr = df_4h['atr'].rolling(20).mean().iloc[-1] if 'atr' in df_4h else 1

            if atr > 1.5 * avg_atr and bb_width > 1.5 * avg_bb_width:
                return MarketRegime.VOLATILE_BREAKOUT
            
            if adx < 20 and bb_width < avg_bb_width:
                return MarketRegime.RANGING
                
            if price > ema50 and ema50 > ema200 and adx > 25:
                return MarketRegime.TRENDING_BULLISH
                
            if price < ema50 and ema50 < ema200 and adx > 25:
                return MarketRegime.TRENDING_BEARISH
                
            return MarketRegime.UNKNOWN
        except Exception as e:
            logger.error(f"Error classifying market regime: {e}")
            return MarketRegime.UNKNOWN

    def get_regime_confidence(self, df: pd.DataFrame) -> float:
        """Calculate confidence of the current regime (0-1)."""
        try:
            if len(df) == 0 or 'adx' not in df:
                return 0.0
                
            adx = df['adx'].iloc[-1]
            
            # Simple confidence based on ADX strength (normalized loosely between 0 and 1)
            confidence = min(max((adx - 10) / 40.0, 0.0), 1.0)
            return confidence
        except Exception as e:
            logger.error(f"Error calculating regime confidence: {e}")
            return 0.0
