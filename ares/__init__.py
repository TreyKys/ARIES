"""
ARES deterministic trading core.

This package is the rebuilt "brain": every trade decision is a pure,
reproducible function of market data. No randomness, no hardcoded values,
and no LLM sits on the trade trigger. The same code path runs in a
backtest, in paper trading, and (once proven) live, so results are
directly comparable.

Layers:
    indicators  - pure numerical indicators (EMA, RSI, ATR, ...)
    strategy    - deterministic Strategy protocol + concrete strategies
    risk        - deterministic position sizing and risk gates
    broker      - PaperBroker with realistic fee/slippage modelling
    backtest    - runs strategy + risk + broker over history -> metrics
    datasource  - load OHLCV from CSV / exchange, or generate for tests
"""

__all__ = [
    "indicators",
    "strategy",
    "risk",
    "broker",
    "backtest",
    "datasource",
    "types",
]
