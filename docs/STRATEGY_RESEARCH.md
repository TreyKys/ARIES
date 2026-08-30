# ARES strategy research: what actually has an edge

Goal: significantly improve ARIES's success rate and profitability — for
real, after costs. This document is deliberately honest. It separates what
the evidence supports from what sounds good but loses money, and turns the
findings into a prioritized list of falsifiable hypotheses to run through
`scripts/run_backtest.py`.

## The honest premise: "nothing predicts the markets"

Half true. You cannot reliably **predict price** — short-horizon returns
are close to a noisy, adversarial random walk, and our own test proved a
plausible-looking strategy loses money on 18 months of real BTC/ETH data
(BTC −1.19R, ETH −0.81R per trade after costs). So "just predict the next
candle" does not work, for us or for anyone.

But markets are only *near*-efficient. Small, sometimes unstable
**structural inefficiencies** persist because they're paid for by real
economic forces (leverage demand, human activity cycles, forced
liquidations). Edge comes from **harvesting those, controlling cost, and
diversifying** — not from prediction. That is the game ARIES should play.

## What the evidence supports (ranked by fit to "low probability of loss")

### 1. Delta-neutral funding-rate / basis carry — the realistic low-risk edge
Long spot + short the perpetual future (or vice-versa) cancels price risk
and collects the funding payment. Studies find it "a stable yet rewarding
alternative to HODL," ~8–18% annualized under stable conditions, and one
delta-neutral basket returned ~12.7% CAGR with a **0.28% max drawdown**.
Caveat: it's crowded — only ~40% of the *top* spread opportunities stay
positive after costs — so selection and cost modelling matter.
**Why it fits you:** this is the only strategy here whose risk profile
actually matches "reduce loss probability to ~10%." It won't 10x $50, but
it's a genuine positive-expectancy, low-drawdown engine.
Sources: [funding-rate arb risk/return](https://www.sciencedirect.com/science/article/pii/S2096720925000818),
[two-tiered funding markets](https://www.mdpi.com/2227-7390/14/2/346).

### 2. Time-series momentum / trend, at higher timeframes (low turnover)
TSMOM is the most robust documented crypto anomaly: pre-cost it beats
cross-sectional momentum (~32% vs ~15% annual) and buy-and-hold on a
risk-adjusted basis. **But** the literature is blunt that returns "may not
be profitable once adjusted for transaction costs." The fix is **low
turnover**: trade the 1h/4h/1d, not 5m. Fewer, bigger moves so costs are a
small fraction of each. Our failed baseline was momentum done at 5m with a
0.3% stop — costs ate ~40% of every move. Same idea, wrong timeframe.
Sources: [Bitcoin intraday TS momentum (Shen 2022)](https://onlinelibrary.wiley.com/doi/abs/10.1111/fire.12290),
[dynamic TS momentum of crypto](https://www.sciencedirect.com/science/article/abs/pii/S1062940821000590).

### 3. Intraday & day-of-week seasonality — as a filter/overlay
Real, documented patterns: Bitcoin's largest returns cluster ~21:00–23:00
UTC and worst ~03:00–04:00 UTC; intraday vs overnight behaviour flips with
whether the NYSE is open; day-of-week effects are localized to specific
intraday windows; there's even a "turn-of-the-candle" effect. These are
small alone but valuable as a **filter** on the strategies above (trade
only in favourable windows) — and unlike the old engine's arbitrary
"killzones," these are backtestable and evidence-based.
Sources: [overnight seasonality in Bitcoin (Quantpedia)](https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin),
[turn-of-the-candle effect](https://pmc.ncbi.nlm.nih.gov/articles/PMC10015199/).

### 4. Mean reversion at higher-timeframe support/resistance — situational
Intraday reversal coexists with momentum in crypto. Works in ranging
regimes, fails in trends — so it must be **regime-gated** (only when a
volatility/trend filter says "range"). Secondary priority.
Source: [intraday momentum/reversal in crypto](https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833).

## What does NOT work (with our own proof)

- **High-frequency micro-scalping on $50.** Mathematically dominated by
  costs. Exchange minimums force a ~$250 notional against a ~$0.75 risk
  budget → a ~0.3% stop → round-trip fees+slippage (~0.12%) consume ~40%
  of every move. Our BTC/ETH backtests are the receipt. "Stack many small
  profits" becomes "stack many fees."
- **An LLM as the trade trigger.** Non-deterministic, slow, no predictive
  training on price. It produces fluent rationales uncorrelated with
  outcomes. Kept off the hot path by design (see `docs/ARCHITECTURE.md`).
- **Curve-fit indicator soup.** "More backtesting → larger gap between
  backtest and live" is an empirically documented overfitting result.
  More indicators/agents ≠ more edge.
  Source: [probability of backtest overfitting](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting).

## The cost & capital reality (must-read)

Two hard truths the $50 goal runs into:

1. **Low loss probability and large growth are in tension.** The low-DD
   strategy (carry) yields ~10–18%/yr — on $50 that's a few dollars a
   year. Strategies that could "10x $50" require concentrated, high-
   variance bets — i.e. high loss probability. You cannot maximise both.
2. **$50 is a learning/validation stake, not a growth engine.** Exchange
   min-notionals (~$5–10) and per-trade costs make small capital
   structurally inefficient. The real objective is a **validated edge you
   can fund properly later**. Prove positive expectancy at $50; scale
   capital, not risk.

## How we avoid fooling ourselves (validation methodology)

Every candidate below must clear this bar before it's allowed near money:

- **Labelling:** triple-barrier (+k·ATR / −k·ATR / timeout).
- **Meta-labelling:** ML only estimates P(win) on setups the deterministic
  rule already found; it filters/sizes, never invents trades.
- **Validation:** purged, embargoed walk-forward / **Combinatorial Purged
  CV (CPCV)** — shown to best mitigate overfitting — plus an untouched
  holdout. Report the **Deflated Sharpe Ratio** and **PBO**.
- **Costs always on.** Fees + slippage in every run (already enforced in
  `ares/broker.py`).
- **Decision rule:** deploy only if expectancy is positive **out-of-sample
  after costs**, with drawdown inside the 10% rule.
Sources: [backtest overfitting in the ML era / CPCV](https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110),
[ML crypto forecasting OOS](https://www.sciencedirect.com/science/article/abs/pii/S0275531923000314).

## The real "coordination and power" (your council, done right)

The valuable version of your multi-agent idea is **not** 27 bots voting on
one 5m candle. It's an **ensemble of uncorrelated strategies** —
delta-neutral carry (market-neutral) + higher-TF trend (long-vol) +
seasonality overlay — run together. Their returns are weakly correlated,
so combined drawdown is far lower than any one alone. *That* is where
coordination lowers loss probability. The "council" becomes a portfolio
allocator over proven edges, each of which passed the bar above.

## Backtest roadmap (prioritized, each a falsifiable hypothesis)

Run each through `scripts/run_backtest.py` (extend the engine as needed):

1. **H1 — Trend on higher TF.** TrendPullback/breakout on 1h & 4h, wider
   ATR stops, target low turnover. Does raising the timeframe flip
   expectancy positive after costs? (Cheapest test; do first.)
2. **H2 — Session/seasonality filter.** Restrict H1 entries to favourable
   UTC windows (e.g. ~13:00–23:00) and weekdays. Does the filter improve
   expectancy vs unfiltered?
3. **H3 — Funding-rate carry.** Build a delta-neutral carry sim (needs
   funding-rate history + a two-leg paper broker). Target: positive
   expectancy, <2% drawdown. Best fit for the low-loss mandate.
4. **H4 — Regime-gated mean reversion.** Bollinger/RSI reversion allowed
   only when a volatility filter flags "range."
5. **H5 — Meta-label filter.** Train the `MetaLabelModel` on H1/H2 setups
   (triple-barrier labels, CPCV). Does P(win) filtering raise expectancy
   out-of-sample?
6. **H6 — Ensemble.** Combine whichever of H1–H5 are positive and weakly
   correlated; measure portfolio drawdown vs the individuals.

Each hypothesis gets a one-line verdict (deploy / iterate / reject) from
real out-of-sample data — not opinion.

### Initial findings (run on 18mo real data)

| Test | BTC | ETH | Verdict |
|------|-----|-----|---------|
| Baseline TrendPullback 5m | −1.19R (216) | −0.81R (614) | reject |
| H1: same rule, 1h | −0.60R (5) | −0.17R (236) | iterate |
| H1: same rule, 4h | +0.86R (3) | −0.35R (54) | inconclusive (tiny n) |

Raising the timeframe **reduced the cost bleed** (ETH −0.81R → −0.17R),
confirming costs — not just signal — were killing the 5m version. But it
did not produce a real edge, and BTC's 3–5 trade samples are noise. The
pullback-entry logic is weak; next iterations should try a cleaner
trend-following entry (e.g. Donchian/breakout) and then move to H3 (carry),
which the literature supports as the stronger low-drawdown edge.

## Bottom line

Can ARIES "beat the market"? Not by prediction. But a disciplined
portfolio of real, cost-aware, validated edges — carry for stability,
higher-TF trend for growth, seasonality as a filter, ML only to sharpen —
is a credible, evidence-based path to positive expectancy with controlled
drawdown. The next concrete step is H1: does trend-following survive costs
on higher timeframes? That we can answer this week, on real data.
