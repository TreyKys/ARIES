# ARES deterministic core (`ares/`)

This package is the rebuilt "brain". It exists to fix the root problem in
the old engine: trade decisions were non-deterministic (an LLM with an
invalid model id was the final trigger) and mixed with faked inputs
(random "retail sentiment", a hardcoded 85% confluence, an empty RAG
"Historian"). None of that could be backtested, so there was no way to
know whether any edge existed.

## Principles

1. **Deterministic trigger.** Every trade decision is a pure function of
   market data. Same candles in → same decision out. That is what makes
   it testable, backtestable, and debuggable.
2. **No fake data.** If a signal isn't computed from real inputs, it
   doesn't exist. No random numbers, no hardcoded scores.
3. **Costs are always modelled.** Fees + slippage are deducted in every
   backtest and paper fill — the thing that quietly kills high-frequency
   micro-account strategies.
4. **One code path.** Backtest, paper, and (eventually) live drive the
   same Strategy → Risk → Broker pipeline, so results are comparable.
5. **The LLM is a sidecar, not the trigger.** Language models are great
   for journaling, research digests, and turning news into a numeric
   feature — all *off* the hot path. They never pull the trigger.

## Modules

| File | Responsibility |
|------|----------------|
| `types.py` | Shared dataclasses (`Candle`, `Side`, `StrategyDecision`, `Trade`, `Costs`, …). |
| `indicators.py` | Pure EMA / SMA / RSI / ATR on numpy arrays. |
| `strategy.py` | `Strategy` protocol + `TrendPullbackStrategy` (deterministic). |
| `risk.py` | Risk-based position sizing + hard gates (drawdown, daily loss, leverage, min notional, adaptive risk). |
| `broker.py` | `PaperBroker` — simulated fills vs. real prices with fees/slippage. |
| `backtest.py` | Runs the pipeline over history → honest metrics. |
| `datasource.py` | Synthetic (deterministic), CSV, or ccxt OHLCV. |

## Run it

```bash
pip install -r requirements.txt

# Smoke test (no network):
python scripts/run_backtest.py --source synthetic

# Real data (on the VPS, where Binance is reachable):
python scripts/run_backtest.py --source ccxt --symbol BTC/USDT --timeframe 5m --candles 1500

# Tests:
python -m pytest tests/ -q
```

## What this is NOT (yet)

- Not wired into the live `core/engine.py` loop — next step is to replace
  the Council/Gemini trigger with `Strategy` + `risk`, keeping the same
  Supabase reporting.
- `TrendPullbackStrategy` is a baseline, **not** a proven edge. Prove or
  reject it with `scripts/run_backtest.py` on real data before risking a
  cent.
