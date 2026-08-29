from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TradingPair:
    symbol: str
    exchange: str
    base: str
    quote: str
    min_qty: float
    qty_precision: int
    price_precision: int
    tick_size: float

WATCHED_PAIRS: List[TradingPair] = [
    TradingPair(
        symbol="BTC/USDT",
        exchange="binance",
        base="BTC",
        quote="USDT",
        min_qty=0.001,
        qty_precision=3,
        price_precision=2,
        tick_size=0.01
    ),
    TradingPair(
        symbol="ETH/USDT",
        exchange="binance",
        base="ETH",
        quote="USDT",
        min_qty=0.01,
        qty_precision=3,
        price_precision=2,
        tick_size=0.01
    ),
    TradingPair(
        symbol="EUR/USD",
        exchange="oanda",
        base="EUR",
        quote="USD",
        min_qty=1.0,
        qty_precision=0,
        price_precision=5,
        tick_size=0.00001
    ),
    TradingPair(
        symbol="GBP/JPY",
        exchange="oanda",
        base="GBP",
        quote="JPY",
        min_qty=1.0,
        qty_precision=0,
        price_precision=3,
        tick_size=0.001
    )
]

def get_pair_by_symbol(symbol: str) -> Optional[TradingPair]:
    for pair in WATCHED_PAIRS:
        if pair.symbol == symbol:
            return pair
    return None

def get_binance_pairs() -> List[TradingPair]:
    return [p for p in WATCHED_PAIRS if p.exchange == "binance"]

def get_oanda_pairs() -> List[TradingPair]:
    return [p for p in WATCHED_PAIRS if p.exchange == "oanda"]
