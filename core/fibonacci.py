import logging

logger = logging.getLogger(__name__)

def calculate_fib_levels(swing_high: float, swing_low: float) -> dict:
    """Calculate standard Fibonacci retracement levels."""
    try:
        diff = swing_high - swing_low
        if diff <= 0:
            return {}
            
        return {
            0.0: swing_high,
            0.236: swing_high - 0.236 * diff,
            0.382: swing_high - 0.382 * diff,
            0.5: swing_high - 0.5 * diff,
            0.618: swing_high - 0.618 * diff,
            0.705: swing_high - 0.705 * diff,
            0.786: swing_high - 0.786 * diff,
            1.0: swing_low
        }
    except Exception as e:
        logger.error(f"Error calculating fib levels: {e}")
        return {}

def get_zone(current_price: float, swing_high: float, swing_low: float) -> str:
    """
    Determine if price is in Premium, Discount, or Equilibrium.
    Premium: > 0.5 fib
    Discount: < 0.5 fib
    Equilibrium: within 2% of the 0.5 level
    """
    try:
        diff = swing_high - swing_low
        if diff <= 0:
            return "UNKNOWN"
            
        eq_level = swing_low + (diff * 0.5)
        tolerance = diff * 0.02
        
        if abs(current_price - eq_level) <= tolerance:
            return 'EQUILIBRIUM'
        elif current_price > eq_level:
            return 'PREMIUM'
        else:
            return 'DISCOUNT'
    except Exception as e:
        logger.error(f"Error determining zone: {e}")
        return "UNKNOWN"

def is_in_ote(current_price: float, swing_high: float, swing_low: float) -> bool:
    """Check if price is within the Optimal Trade Entry zone (0.618 - 0.786)."""
    try:
        fibs = calculate_fib_levels(swing_high, swing_low)
        if not fibs:
            return False
            
        # OTE range
        upper = max(fibs[0.618], fibs[0.786])
        lower = min(fibs[0.618], fibs[0.786])
        
        return lower <= current_price <= upper
    except Exception as e:
        logger.error(f"Error checking OTE: {e}")
        return False

def get_fib_level_at_price(price: float, swing_high: float, swing_low: float) -> float:
    """Return the precise fib level (0-1) for a given price."""
    try:
        diff = swing_high - swing_low
        if diff <= 0:
            return 0.0
            
        # Since 1.0 is swing_low and 0.0 is swing_high:
        return (swing_high - price) / diff
    except Exception as e:
        logger.error(f"Error getting fib level: {e}")
        return 0.0
