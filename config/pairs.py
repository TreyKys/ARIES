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

# Automatically scaling to 20 High-Liquidity Pairs
binance_tickers = ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "AVAX", "DOGE", "DOT", "LINK", "MATIC", "INJ", "RNDR", "OP", "ARB", "SUI", "APT", "NEAR", "FTM", "TIA"]

WATCHED_PAIRS: List[TradingPair] = []
for ticker in binance_tickers:
    WATCHED_PAIRS.append(TradingPair(
        symbol=f"{ticker}/USDT",
        exchange="binance",
        base=ticker,
        quote="USDT",
        min_qty=0.1 if ticker not in ['BTC', 'ETH'] else 0.001,
        qty_precision=1 if ticker not in ['BTC', 'ETH'] else 3,
        price_precision=4 if ticker not in ['BTC', 'ETH'] else 2,
        tick_size=0.0001 if ticker not in ['BTC', 'ETH'] else 0.01
    ))

def get_pair_by_symbol(symbol: str) -> Optional[TradingPair]:
    for pair in WATCHED_PAIRS:
        if pair.symbol == symbol:
            return pair
    return None

def get_binance_pairs() -> List[TradingPair]:
    return [p for p in WATCHED_PAIRS if p.exchange == "binance"]

def get_oanda_pairs() -> List[TradingPair]:
    return [p for p in WATCHED_PAIRS if p.exchange == "oanda"]
