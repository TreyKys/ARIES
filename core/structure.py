import logging
from enum import Enum
from typing import List, Optional
import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"

class StructureType(str, Enum):
    HH = "HH"  # Higher High
    HL = "HL"  # Higher Low
    LH = "LH"  # Lower High
    LL = "LL"  # Lower Low
    UNCONFIRMED = "UNCONFIRMED"

class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"

class BlockType(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"

class SwingPoint(BaseModel):
    index: int
    price: float
    type: SwingType
    structure: StructureType

class BOS(BaseModel):
    index: int
    price: float
    direction: TrendDirection
    level: float

class CHoCH(BaseModel):
    index: int
    price: float
    new_direction: TrendDirection

class OrderBlock(BaseModel):
    start_idx: int
    end_idx: int
    high: float
    low: float
    type: BlockType
    mitigated: bool = False
    timeframe: str = "1h"

class FVG(BaseModel):
    index: int
    high: float
    low: float
    type: BlockType
    mitigated: bool = False
    timeframe: str = "1h"

class StructureAnalyzer:
    def __init__(self):
        pass

    def find_swing_points(self, df: pd.DataFrame, lookback: int = 5) -> List[SwingPoint]:
        """Identifies swing highs and lows based on local extrema."""
        swings = []
        try:
            highs = df['high'].values
            lows = df['low'].values
            
            last_high_price = -1.0
            last_low_price = float('inf')
            
            for i in range(lookback, len(df) - lookback):
                is_swing_high = True
                is_swing_low = True
                
                for j in range(1, lookback + 1):
                    if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                        is_swing_high = False
                    if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                        is_swing_low = False
                        
                if is_swing_high:
                    struct = StructureType.UNCONFIRMED
                    if last_high_price != -1.0:
                        struct = StructureType.HH if highs[i] > last_high_price else StructureType.LH
                    swings.append(SwingPoint(index=i, price=highs[i], type=SwingType.SWING_HIGH, structure=struct))
                    last_high_price = highs[i]
                    
                if is_swing_low:
                    struct = StructureType.UNCONFIRMED
                    if last_low_price != float('inf'):
                        struct = StructureType.HL if lows[i] > last_low_price else StructureType.LL
                    swings.append(SwingPoint(index=i, price=lows[i], type=SwingType.SWING_LOW, structure=struct))
                    last_low_price = lows[i]
                    
            return swings
        except Exception as e:
            logger.error(f"Error finding swing points: {e}")
            return []

    def detect_bos(self, swings: List[SwingPoint], direction: TrendDirection) -> List[BOS]:
        """Detect Break of Structure."""
        bos_list = []
        if len(swings) < 3:
            return bos_list
            
        try:
            # Simplistic approach: if we form a HH in a bullish trend, the previous SWING_HIGH was broken.
            for i in range(2, len(swings)):
                curr = swings[i]
                prev = swings[i-2] # previous swing of same type usually
                
                if direction == TrendDirection.BULLISH and curr.structure == StructureType.HH and curr.type == SwingType.SWING_HIGH:
                    # Look back to find the broken level
                    bos_list.append(BOS(index=curr.index, price=curr.price, direction=direction, level=prev.price))
                elif direction == TrendDirection.BEARISH and curr.structure == StructureType.LL and curr.type == SwingType.SWING_LOW:
                    bos_list.append(BOS(index=curr.index, price=curr.price, direction=direction, level=prev.price))
                    
            return bos_list
        except Exception as e:
            logger.error(f"Error detecting BOS: {e}")
            return []

    def detect_choch(self, swings: List[SwingPoint], current_trend: TrendDirection) -> List[CHoCH]:
        """Detect Change of Character."""
        choch_list = []
        try:
            for i in range(1, len(swings)):
                curr = swings[i]
                if current_trend == TrendDirection.BULLISH and curr.structure == StructureType.LL:
                    choch_list.append(CHoCH(index=curr.index, price=curr.price, new_direction=TrendDirection.BEARISH))
                elif current_trend == TrendDirection.BEARISH and curr.structure == StructureType.HH:
                    choch_list.append(CHoCH(index=curr.index, price=curr.price, new_direction=TrendDirection.BULLISH))
            return choch_list
        except Exception as e:
            logger.error(f"Error detecting CHoCH: {e}")
            return []

    def find_order_blocks(self, df: pd.DataFrame, displacement_threshold: float = 2.0) -> List[OrderBlock]:
        """Find Order Blocks (last opposite candle before strong displacement)."""
        obs = []
        try:
            if 'atr' not in df.columns:
                from .indicators import compute_atr
                df['atr'] = compute_atr(df, 14)
                
            for i in range(1, len(df)):
                body = abs(df['close'].iloc[i] - df['open'].iloc[i])
                atr = df['atr'].iloc[i]
                
                if body > displacement_threshold * atr:
                    # Displacement found
                    is_bullish_disp = df['close'].iloc[i] > df['open'].iloc[i]
                    
                    if is_bullish_disp:
                        # Find last bearish candle
                        for j in range(i-1, -1, -1):
                            if df['close'].iloc[j] < df['open'].iloc[j]:
                                obs.append(OrderBlock(
                                    start_idx=j, end_idx=i,
                                    high=df['high'].iloc[j], low=df['low'].iloc[j],
                                    type=BlockType.BULLISH
                                ))
                                break
                    else:
                        # Find last bullish candle
                        for j in range(i-1, -1, -1):
                            if df['close'].iloc[j] > df['open'].iloc[j]:
                                obs.append(OrderBlock(
                                    start_idx=j, end_idx=i,
                                    high=df['high'].iloc[j], low=df['low'].iloc[j],
                                    type=BlockType.BEARISH
                                ))
                                break
            return obs
        except Exception as e:
            logger.error(f"Error finding order blocks: {e}")
            return []

    def find_fvg(self, df: pd.DataFrame) -> List[FVG]:
        """Find Fair Value Gaps."""
        fvgs = []
        try:
            for i in range(2, len(df)):
                # Bullish FVG
                if df['low'].iloc[i] > df['high'].iloc[i-2]:
                    fvgs.append(FVG(
                        index=i,
                        high=df['low'].iloc[i],
                        low=df['high'].iloc[i-2],
                        type=BlockType.BULLISH
                    ))
                # Bearish FVG
                elif df['high'].iloc[i] < df['low'].iloc[i-2]:
                    fvgs.append(FVG(
                        index=i,
                        high=df['low'].iloc[i-2],
                        low=df['high'].iloc[i],
                        type=BlockType.BEARISH
                    ))
            return fvgs
        except Exception as e:
            logger.error(f"Error finding FVGs: {e}")
            return []

    def check_mitigation(self, ob_or_fvg: BaseModel, current_price: float) -> bool:
        """Check if price has returned to the order block or FVG zone."""
        if hasattr(ob_or_fvg, 'high') and hasattr(ob_or_fvg, 'low'):
            return ob_or_fvg.low <= current_price <= ob_or_fvg.high
        return False

    def get_current_trend(self, swings: List[SwingPoint]) -> str:
        """Get current trend based on swing sequence."""
        if len(swings) < 2:
            return TrendDirection.RANGING.value
            
        last_swings = [s.structure for s in swings[-4:]]
        if StructureType.HH in last_swings and StructureType.HL in last_swings:
            return TrendDirection.BULLISH.value
        elif StructureType.LH in last_swings and StructureType.LL in last_swings:
            return TrendDirection.BEARISH.value
            
        return TrendDirection.RANGING.value
