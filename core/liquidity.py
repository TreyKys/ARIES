import logging
from enum import Enum
from typing import List, Tuple
import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SweepType(str, Enum):
    BSL_SWEEP = "BSL_SWEEP"
    SSL_SWEEP = "SSL_SWEEP"

class LiquiditySweep(BaseModel):
    index: int
    level: float
    type: SweepType
    wick_distance: float

class LiquidityMap(BaseModel):
    bsl_levels: List[float]
    ssl_levels: List[float]
    recent_sweeps: List[LiquiditySweep]

class LiquidityMapper:
    def __init__(self):
        pass

    def find_equal_highs(self, df: pd.DataFrame, tolerance_pct: float = 0.001) -> List[float]:
        """Find Equal Highs representing Buy-Side Liquidity (BSL)."""
        eq_highs = []
        try:
            highs = df['high'].values
            for i in range(len(highs)):
                for j in range(i + 5, min(len(highs), i + 50)):
                    tolerance = highs[i] * tolerance_pct
                    if abs(highs[i] - highs[j]) <= tolerance:
                        eq_highs.append((highs[i] + highs[j]) / 2.0)
            # Filter close levels
            eq_highs = sorted(list(set([round(x, 4) for x in eq_highs])))
            return eq_highs
        except Exception as e:
            logger.error(f"Error finding equal highs: {e}")
            return []

    def find_equal_lows(self, df: pd.DataFrame, tolerance_pct: float = 0.001) -> List[float]:
        """Find Equal Lows representing Sell-Side Liquidity (SSL)."""
        eq_lows = []
        try:
            lows = df['low'].values
            for i in range(len(lows)):
                for j in range(i + 5, min(len(lows), i + 50)):
                    tolerance = lows[i] * tolerance_pct
                    if abs(lows[i] - lows[j]) <= tolerance:
                        eq_lows.append((lows[i] + lows[j]) / 2.0)
            eq_lows = sorted(list(set([round(x, 4) for x in eq_lows])))
            return eq_lows
        except Exception as e:
            logger.error(f"Error finding equal lows: {e}")
            return []

    def detect_liquidity_sweep(self, df: pd.DataFrame, levels: List[float]) -> List[LiquiditySweep]:
        """Detect when price wicks beyond a liquidity level but closes back inside."""
        sweeps = []
        try:
            for i in range(len(df)):
                high = df['high'].iloc[i]
                low = df['low'].iloc[i]
                close = df['close'].iloc[i]
                open_px = df['open'].iloc[i]
                
                max_body = max(open_px, close)
                min_body = min(open_px, close)
                
                for level in levels:
                    # BSL Sweep: High breaks level, body closes below level
                    if high > level > max_body:
                        sweeps.append(LiquiditySweep(
                            index=i, level=level,
                            type=SweepType.BSL_SWEEP, wick_distance=high - level
                        ))
                    
                    # SSL Sweep: Low breaks level, body closes above level
                    if low < level < min_body:
                        sweeps.append(LiquiditySweep(
                            index=i, level=level,
                            type=SweepType.SSL_SWEEP, wick_distance=level - low
                        ))
            return sweeps
        except Exception as e:
            logger.error(f"Error detecting liquidity sweeps: {e}")
            return []

    def get_nearest_liquidity(self, price: float, levels: List[float]) -> Tuple[float, float]:
        """Returns the nearest BSL above and nearest SSL below current price."""
        try:
            above = [lvl for lvl in levels if lvl > price]
            below = [lvl for lvl in levels if lvl < price]
            
            nearest_bsl = min(above) if above else float('inf')
            nearest_ssl = max(below) if below else 0.0
            
            return nearest_bsl, nearest_ssl
        except Exception as e:
            logger.error(f"Error getting nearest liquidity: {e}")
            return float('inf'), 0.0

    def map_all(self, df: pd.DataFrame) -> LiquidityMap:
        """Map all liquidity pools and sweeps."""
        try:
            bsl = self.find_equal_highs(df)
            ssl = self.find_equal_lows(df)
            all_levels = bsl + ssl
            sweeps = self.detect_liquidity_sweep(df, all_levels)
            
            return LiquidityMap(
                bsl_levels=bsl,
                ssl_levels=ssl,
                recent_sweeps=sweeps
            )
        except Exception as e:
            logger.error(f"Error mapping all liquidity: {e}")
            return LiquidityMap(bsl_levels=[], ssl_levels=[], recent_sweeps=[])
