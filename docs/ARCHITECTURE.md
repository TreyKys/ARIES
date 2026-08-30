# ARES architecture: deterministic core + ML/LLM slots

The governing rule:

> **Anything that can change which trade fires must be reproducible and
> backtestable at the instant it fires.**

So the hot path (tick → order) is 100% deterministic. ML and LLMs are
allowed to influence it, but only in reproducible forms — never as a live
free-text call standing on the trigger.

## Who owns each decision stage

| # | Stage | Owner | Hot path? | Reproducible? |
|---|-------|-------|-----------|----------------|
| 1 | Ingest OHLCV / order book / funding | Deterministic | ✅ | yes |
| 2 | Indicators, structure, imbalance (`ares/indicators.py`, `features.py`) | Deterministic | ✅ | yes |
| 3 | Regime / volatility / **win-probability** (`ares/ml/`) | ML model, frozen weights | ✅ | yes — saved artifact, µs, same in→same out |
| 4 | Sentiment score + event-risk flag | LLM (async) → written as a **number** | reads a cached number | yes — hot path reads last value; stale/missing = neutral |
| 5 | Strategy: features → decision or None (`ares/strategy.py`) | Deterministic | ✅ | yes |
| 6 | Risk sizing + gates (`ares/risk.py`) | Deterministic | ✅ | yes |
| 7 | Order routing / position mgmt (`ares/broker.py`, live broker TODO) | Deterministic | ✅ | yes |
| 8 | Post-trade journal / daily post-mortem | LLM (async) | ❌ off path | human-facing only |
| 9 | Learning loop: outcomes → retrain / re-tune | ML + backtest, human-gated | ❌ offline | yes — ships only after out-of-sample validation |

```
        ┌──────────────── HOT PATH (deterministic, ms) ────────────────┐
 data → features → [ML artifact: win-prob] → strategy → risk → execute → manage
            ▲                                    ▲
            │ reads a cached NUMBER               │ reads a saved MODEL FILE
   ┌────────┴─────────┐               ┌──────────┴───────────┐
   │  LLM SIDECAR      │               │  ML TRAINING (offline)│
   │ (async, Oracle)   │               │ (offline, Oracle VM)  │
   │ news→sentiment#   │               │ history→labels→model  │
   │ daily journal     │               │ walk-forward validate │
   └──────────────────┘               └──────────────────────┘
```

## The only three ways intelligence may touch a trade

1. **A versioned model artifact** with frozen weights, loaded at startup →
   `FeatureBundle.ml_win_prob` (stage 3).
2. **A timestamped numeric feature** in the bundle (`sentiment`,
   `event_risk`); hot path reads the latest, treats missing/stale as
   neutral (stage 4).
3. **A gated config/param change** that passed the backtester
   out-of-sample. An LLM or human may *propose*; the backtest decides.

Banned by construction: a live `generate_content()` on the trigger (what
the old engine did). The slot for legitimate intelligence is
`ares/features.py::FeatureBundle` — deterministic indicators plus optional
`ml_win_prob` / `sentiment` / `event_risk`, each ignored when absent.

## Where the ML intelligence comes from

- **Data:** `data.binance.vision` (years of free OHLCV; not geo-blocked
  like the trading API), Binance funding/OI, Glassnode/CryptoQuant
  (freemium), OANDA for forex, an economic calendar for `event_risk`.
- **Labels:** triple-barrier labelling (did price hit +k·ATR / −k·ATR /
  neither within N bars) and **meta-labelling** — keep the deterministic
  strategy as the primary signal; train ML only to estimate P(win) and
  thereby size up / down / skip. (This is the "Historian" done right.)
- **Models:** gradient-boosted trees (LightGBM/XGBoost) on engineered
  features; a logistic-regression baseline first. Deep nets last, rarely
  worth it here.
- **Validation:** purged/embargoed walk-forward CV + an untouched holdout.
  Bar to clear: the ML-filtered strategy must beat the raw rule **after
  costs, out-of-sample**. ML sharpens an existing edge; it cannot create
  one.
- **Deploy:** train offline (great use of Oracle VM credits) → export
  artifact → deterministic core loads it → same code path in backtest and
  live → monitor drift → retrain on schedule, versioned. Never mutate
  weights live.

## Oracle credits mapping (the "GenAI vs Gemini" answer)

- **Oracle VM compute** → ML training + backtesting, and hosting the 24/7
  engine. Best use of credits (real compute, not per-token).
- **Oracle GenAI (Cohere/Llama)** → async LLM sidecar: news→sentiment
  number + journaling. Off the hot path, pennies.
- The trigger itself costs nothing per decision (pure Python + a small
  model file).

## Empirical status (real data, 18 months, BTC & ETH 5m)

The baseline `TrendPullbackStrategy` has **negative expectancy** after
costs (BTC −1.19R, ETH −0.81R over the full sample). A dominant cause is
cost structure: on a $50 account, exchange minimums force a large notional
against a tiny risk budget, so round-trip fees + slippage consume a big
fraction of every move. See `docs/STRATEGY_RESEARCH.md` for the plan to
find a real edge and the sizing implications.
```
