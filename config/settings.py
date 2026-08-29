import os
from enum import Enum
from functools import lru_cache
from typing import Tuple, List
from pydantic_settings import BaseSettings, SettingsConfigDict

class EngineMode(str, Enum):
    MONITOR = 'MONITOR'
    PAPER = 'PAPER'
    LIVE = 'LIVE'

class Settings(BaseSettings):
    # Risk parameters
    STARTING_CAPITAL: float = 50.0
    MAX_RISK_PER_TRADE: float = 0.015
    MAX_DAILY_DRAWDOWN: float = 0.04
    MAX_TOTAL_DRAWDOWN: float = 0.10
    MIN_RR_RATIO: float = 2.0
    MIN_CONFIDENCE: float = 0.80

    # Adaptive calibration
    CONSEC_LOSS_THRESHOLD: int = 2
    REDUCED_RISK: float = 0.005
    RECOVERY_WINS_NEEDED: int = 2

    # Execution
    DEFAULT_LEVERAGE: int = 5
    ORDER_TYPE: str = 'LIMIT'
    SLIPPAGE_BUFFER: float = 0.0005
    MAKER_FEE: float = 0.0002
    TAKER_FEE: float = 0.0005
    ORDER_FILL_TIMEOUT_SECONDS: int = 900

    # Session killzones (UTC hours)
    LONDON_OPEN: Tuple[int, int] = (7, 10)
    NEW_YORK_OPEN: Tuple[int, int] = (12, 15)
    ASIA_RANGE: Tuple[int, int] = (0, 3)

    # News
    NEWS_BUFFER_MINUTES: int = 15

    # Engine
    MODE: EngineMode = EngineMode.PAPER
    TIMEFRAMES: List[str] = ['1m', '5m', '15m', '1h', '4h', '1d']
    SCAN_INTERVAL_SECONDS: int = 5

    # API
    API_HOST: str = '0.0.0.0'
    API_PORT: int = 8080

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Exchange keys
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET: str = ""
    OANDA_API_KEY: str = ""
    OANDA_ACCOUNT_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
