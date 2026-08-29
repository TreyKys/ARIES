import logging
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Any

logger = logging.getLogger(__name__)

class RiskTier(Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    PURPLE = "PURPLE"
    BLACK = "BLACK"

@dataclass
class RiskDecision:
    approved: bool
    reason: str
    risk_tier: RiskTier

class RiskManager:
    def __init__(self, settings: Any):
        self.settings = settings
        self.halt_until: Optional[datetime] = None

    def validate(self, signal: Any, account_state: Any) -> RiskDecision:
        """Validates a trading signal against risk rules."""
        # 1. Is engine halted?
        is_halted, halt_reason, halt_until = self.should_halt(account_state)
        if is_halted:
            return RiskDecision(False, f"ENGINE_HALTED: {halt_reason}", self.update_risk_tier(account_state))

        # Update risk tier
        risk_tier = self.update_risk_tier(account_state)

        # 2. Daily drawdown >= MAX_DAILY_DD?
        max_daily_dd = getattr(self.settings, 'MAX_DAILY_DD', 0.04)
        if account_state.get('daily_dd', 0.0) >= max_daily_dd:
            self.halt_until = datetime.now(timezone.utc) + timedelta(hours=24)
            return RiskDecision(False, "DAILY_DD_LIMIT", risk_tier)

        # 3. Total drawdown >= MAX_TOTAL_DD?
        max_total_dd = getattr(self.settings, 'MAX_TOTAL_DD', 0.10)
        if account_state.get('total_dd', 0.0) >= max_total_dd:
            return RiskDecision(False, "TOTAL_DD_LIMIT", RiskTier.PURPLE)

        # 4. R:R < MIN_RR_RATIO?
        min_rr = getattr(self.settings, 'MIN_RR_RATIO', 1.0)
        from .sizing import calculate_rr_ratio
        # Assume signal has entry_price, stop_loss, take_profit
        rr = calculate_rr_ratio(signal.entry_price, signal.stop_loss, signal.take_profit)
        if rr < min_rr:
            return RiskDecision(False, "RR_TOO_LOW", risk_tier)

        # 5. Confidence < MIN_CONFIDENCE?
        min_confidence = getattr(self.settings, 'MIN_CONFIDENCE', 0.5)
        if getattr(signal, 'confidence', 1.0) < min_confidence:
            return RiskDecision(False, "CONFIDENCE_TOO_LOW", risk_tier)

        # 6. News blackout active?
        if getattr(self.settings, 'NEWS_BLACKOUT', False):
            return RiskDecision(False, "NEWS_BLACKOUT", risk_tier)

        # 7. Outside killzone?
        if not self.is_in_killzone():
            return RiskDecision(False, "OUTSIDE_KILLZONE", risk_tier)

        # 8. Already has open position on this symbol?
        # Assuming account_state has a list of open symbols
        open_positions = account_state.get('open_positions', [])
        if signal.symbol in open_positions:
            return RiskDecision(False, "POSITION_EXISTS", risk_tier)

        # 9. Liquidation price within 2x SL distance?
        from .sizing import calculate_liquidation_price
        liq_price = calculate_liquidation_price(
            signal.entry_price, 
            getattr(self.settings, 'DEFAULT_LEVERAGE', 1), 
            signal.side
        )
        sl_distance = abs(signal.entry_price - signal.stop_loss)
        liq_distance = abs(signal.entry_price - liq_price)
        if liq_distance <= 2 * sl_distance:
            return RiskDecision(False, "LIQUIDATION_SAFETY", risk_tier)

        # 10. Trade not viable after fees/slippage?
        # In a full implementation, we'd calculate expectancy. Here we simulate.
        if sl_distance == 0:
            return RiskDecision(False, "NEGATIVE_EXPECTANCY", risk_tier)

        return RiskDecision(True, "APPROVED", risk_tier)

    def get_current_risk_pct(self, account_state: Any) -> float:
        """Returns the risk percentage based on account state."""
        consecutive_losses = account_state.get('consecutive_losses', 0)
        threshold = getattr(self.settings, 'LOSS_THRESHOLD', 3)
        if consecutive_losses >= threshold:
            return getattr(self.settings, 'REDUCED_RISK_PCT', 0.005)
        return getattr(self.settings, 'NORMAL_RISK_PCT', 0.015)

    def update_risk_tier(self, account_state: Any) -> RiskTier:
        """Determines the current risk tier."""
        if account_state.get('circuit_breaker', False):
            return RiskTier.BLACK
            
        total_dd = account_state.get('total_dd', 0.0)
        if total_dd >= getattr(self.settings, 'MAX_TOTAL_DD', 0.10):
            return RiskTier.PURPLE
            
        daily_dd = account_state.get('daily_dd', 0.0)
        if daily_dd >= getattr(self.settings, 'MAX_DAILY_DD', 0.04):
            return RiskTier.RED
            
        consecutive_losses = account_state.get('consecutive_losses', 0)
        if consecutive_losses >= 2 or (0.02 <= daily_dd < 0.03):
            return RiskTier.AMBER
            
        return RiskTier.GREEN

    def should_halt(self, account_state: Any) -> Tuple[bool, str, Optional[datetime]]:
        """Checks if the engine should be halted."""
        if self.halt_until and datetime.now(timezone.utc) < self.halt_until:
            return True, "HALT_TIMER_ACTIVE", self.halt_until
            
        tier = self.update_risk_tier(account_state)
        if tier == RiskTier.BLACK:
            return True, "CIRCUIT_BREAKER", None
        elif tier == RiskTier.PURPLE:
            return True, "TOTAL_DD_LIMIT", None
        elif tier == RiskTier.RED:
            return True, "DAILY_DD_LIMIT", None
            
        return False, "", None

    def is_in_killzone(self) -> bool:
        """Checks if current UTC time is within a killzone session."""
        current_hour = datetime.now(timezone.utc).hour
        # Example killzones: 7-10 UTC (London), 13-16 UTC (New York)
        killzones = getattr(self.settings, 'KILLZONES', [(7, 10), (13, 16)])
        
        for start, end in killzones:
            if start <= current_hour < end:
                return True
        return False
