from enum import Enum
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class MarketRegime(str, Enum):
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    VOLATILE_BREAKOUT = "VOLATILE_BREAKOUT"

class RiskTier(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    PURPLE = "PURPLE"
    BLACK = "BLACK"

class EngineMode(str, Enum):
    MONITOR = "MONITOR"
    PAPER = "PAPER"
    LIVE = "LIVE"

class SignalAction(str, Enum):
    BUY_LONG = "BUY_LONG"
    SELL_SHORT = "SELL_SHORT"
    HOLD_NO_TRADE = "HOLD_NO_TRADE"

class SignalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class TradeStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL_CLOSED = "PARTIAL_CLOSED"
    CLOSED = "CLOSED"

class EngineStatus(str, Enum):
    ARMED = "ARMED"
    HALTED = "HALTED"
    ERROR = "ERROR"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    
class TradeSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class Signal(BaseModel):
    id: str
    timestamp: datetime
    symbol: str
    market_regime: MarketRegime
    action: SignalAction
    confidence_score: float = Field(ge=0.0, le=1.0)
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    position_size: float
    leverage: int
    rr_ratio: float
    invalidation: str
    abstention_reason: Optional[str] = None
    status: SignalStatus = SignalStatus.PENDING

class Trade(BaseModel):
    id: str
    signal_id: str
    symbol: str
    side: TradeSide
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    position_size: float
    leverage: int
    pnl_usd: Optional[float] = None
    pnl_pct: Optional[float] = None
    r_multiple: Optional[float] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None
    entry_efficiency: Optional[float] = None
    exit_efficiency: Optional[float] = None
    duration_seconds: Optional[int] = None
    strategy: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    notes: Optional[str] = None

class EquitySnapshot(BaseModel):
    timestamp: datetime
    balance: float
    unrealized_pnl: float
    daily_drawdown_pct: float
    total_drawdown_pct: float
    risk_tier: RiskTier

class Position(BaseModel):
    id: str
    symbol: str
    side: TradeSide
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    position_size: float
    remaining_size: float
    leverage: int
    unrealized_pnl: float
    mfe: float = 0.0
    mae: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    opened_at: datetime
    tp1_hit: bool = False
    trailing_active: bool = False
    trailing_stop_price: Optional[float] = None

class AccountState(BaseModel):
    balance: float
    starting_balance: float
    equity: float
    unrealized_pnl: float
    daily_pnl: float
    daily_drawdown_pct: float
    total_drawdown_pct: float
    peak_balance: float
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    win_rate: float = 0.0
    current_risk_pct: float
    risk_tier: RiskTier
    open_positions: List[Position] = Field(default_factory=list)
    is_halted: bool = False
    halt_reason: Optional[str] = None
    halt_until: Optional[datetime] = None

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class EngineHeartbeat(BaseModel):
    timestamp: datetime
    mode: EngineMode
    status: EngineStatus
    active_pairs: List[str]
    open_positions_count: int
    risk_tier: RiskTier
    next_scan: datetime
    uptime_seconds: int
