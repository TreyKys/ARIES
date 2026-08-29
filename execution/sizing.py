import math
from dataclasses import dataclass
from typing import Tuple

@dataclass
class PositionSizeResult:
    position_size: float
    risk_amount_usd: float
    margin_required: float
    notional_value: float
    fee_cost_round_trip: float

def calculate_position_size(
    balance: float,
    risk_pct: float,
    entry_price: float,
    stop_loss_price: float,
    fee_rate: float = 0.0002,
    slippage: float = 0.0005
) -> PositionSizeResult:
    """Calculates position size based on risk parameters."""
    risk_amount = balance * risk_pct
    sl_distance = abs(entry_price - stop_loss_price)
    spread_cost = entry_price * slippage
    effective_sl = sl_distance + spread_cost
    
    # Avoid division by zero
    if effective_sl == 0:
        position_size = 0.0
    else:
        position_size = risk_amount / effective_sl
        
    notional_value = position_size * entry_price
    # Assume isolated margin for simplistic calculation, margin = notional / leverage (leverage is not given here, 
    # but the prompt specifies calculating margin separately or maybe we return an estimate).
    # Wait, the prompt says return margin_required in PositionSizeResult but calculate_margin takes leverage.
    # We will assume a default leverage of 1 or leave it as notional for now. Let's just pass notional.
    margin_required = notional_value # Assuming 1x leverage, will be updated via calculate_margin later
    
    fee_cost_round_trip = notional_value * fee_rate * 2
    
    return PositionSizeResult(
        position_size=position_size,
        risk_amount_usd=risk_amount,
        margin_required=margin_required,
        notional_value=notional_value,
        fee_cost_round_trip=fee_cost_round_trip
    )

def calculate_margin(position_size: float, entry_price: float, leverage: float) -> float:
    """Calculates the margin required for a position."""
    if leverage <= 0:
        return 0.0
    return (position_size * entry_price) / leverage

def calculate_liquidation_price(entry_price: float, leverage: float, side: str, maint_margin_rate: float = 0.005) -> float:
    """Calculates the liquidation price."""
    if leverage <= 0:
        return 0.0
    
    side = side.upper()
    if side == "LONG":
        return entry_price * (1 - 1 / leverage + maint_margin_rate)
    elif side == "SHORT":
        return entry_price * (1 + 1 / leverage - maint_margin_rate)
    else:
        raise ValueError(f"Invalid side: {side}")

def calculate_rr_ratio(entry: float, stop_loss: float, take_profit: float) -> float:
    """Calculates the Risk/Reward ratio."""
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk == 0:
        return 0.0
    return reward / risk

def round_to_precision(value: float, precision: int) -> float:
    """Rounds a value to N decimal places."""
    factor = 10 ** precision
    return math.floor(value * factor) / factor

def validate_position_viable(
    position_size: float,
    entry_price: float,
    leverage: float,
    balance: float,
    min_qty: float,
    qty_precision: int
) -> Tuple[bool, str]:
    """Validates if a position is viable given constraints."""
    margin = calculate_margin(position_size, entry_price, leverage)
    
    if margin > balance:
        return False, f"Margin required ({margin}) exceeds balance ({balance})"
        
    rounded_qty = round_to_precision(position_size, qty_precision)
    if rounded_qty < min_qty:
        return False, f"Position size ({rounded_qty}) is below minimum quantity ({min_qty})"
        
    return True, "Valid"
