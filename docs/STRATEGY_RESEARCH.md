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

## Findings v2 — trying to beat PF 1.6 (honest results)

Attempts to raise the breakout's profit factor, tested in-sample (2024)
then out-of-sample (2025), pooled across ETH/SOL/AVAX/LINK 4h:

- **Trend filter (EMA-50): no effect.** A 55-bar breakout is already an
  uptrend, so the filter is redundant. Null result, kept out.
- **Trailing stops: helped in some configs but did NOT survive honest
  parameter selection.** Tuning the trail distance on 2024 and testing on
  2025 showed the in-sample best (5·ATR, PF 1.24) became an out-of-sample
  loser (PF 0.75); a config that looked great OOS (2·ATR) was terrible
  in-sample. The IS/OOS relationship was essentially noise -> classic
  overfitting. **Conclusion: the directional breakout edge on these alts
  is weak and fragile.** Do not trust a tuned directional PF.

This is the empirical version of "statistical edges are unstable."
Structural edges are not, because they don't predict anything:

- **Carry is the robust edge.** Per-pair always-on carry: ETH 9.9%/yr,
  LINK 9.9%, SOL 8.8%, AVAX 6.8% annualized, collecting *positive* funding
  **71–91% of intervals**, max drawdown <1.5%. That is genuinely
  "profits beat losses, consistently" — a structurally high profit factor.
- **Diversifying carry across pairs** smooths the ride but (this period)
  didn't raise yield — alt funding ≈ ETH funding.
- **The one legitimate lever is leverage on the price-neutral carry:**
  1x→10%/yr, 2x→19%, 3x→28%, 5x→46%. Real (funding-arb funds do this),
  with bounded added risk (negative-funding stretches, basis/liquidation
  on the short leg) — NOT the ruin risk of directional leverage.

**Revised recommendation:** make the **multi-pair carry (optionally 2–3x)**
the core engine — it is the real, robust "win more than lose" machine.
Treat breakout as a small, *untuned* satellite with modest expectations,
not the core. Do not parameter-tune the directional strategy into false
confidence.

## League results (crypto + forex, 147 OOS backtests)

`scripts/league.py` scores every strategy x pair x timeframe on 2025
(out-of-sample), crypto and forex, with asset-appropriate costs. Robust
aggregate findings (not cherry-picked single configs):

- **Timeframe is the biggest lever: 4h is the edge zone** — 53% of 4h
  configs profitable (median PF 1.01) vs 1h 24% (0.88); 1d too sparse.
- **Crypto >> forex majors** — crypto 50% of configs profitable, forex
  19%. FX majors are too efficient for this trend/breakout style, so the
  original EUR/USD, GBP/JPY plan is the *weakest* ground.
- **No strategy wins on a typical pair** (median PF ~0.9). Edge is
  concentrated in specific names (SOL, ETH) on 4h -> trade a **curated
  basket**, not everything.
- **Standout OOS configs:** SOL 4h breakout PF ~1.9 (+0.43R, 80% positive
  months), ETH 4h PF ~1.8 (80% positive months). Real candidates, but they
  sit atop a roughly-breakeven distribution, so **walk-forward across
  multiple periods is required before trusting** (single-period selection
  bias).

**Tuned configuration this points to:** 4h timeframe, crypto (ETH/SOL core,
LINK/AVAX secondary), breakout family (fixed or trailing), as a curated
basket layered on the carry core. Forex majors deprioritized. Full table:
`data/league_results.csv`.

## Arbitrage battle-test (deep session)

Built and stress-tested the arbitrage families on real data:

- **Cross-exchange / triangular arb:** ruled out for a small account —
  research and cost math agree it's an infrastructure race retail loses
  (need >0.2% gaps just to clear fees; latency-dominated).
- **Statistical arbitrage (pairs trading, `ares/statarb.py`):** real edge
  exists (winning pairs OOS at PF 2–3.7, e.g. BNB/SOL 70% win) but it is
  **weak and does not generalize**: strict cointegration selects ~nothing;
  correlation selection gives 9/20 profitable but an equal-weight book only
  ~3%/yr; picking winners by in-sample Sharpe FAILS out-of-sample
  (+2–4%/yr); 1h loses to costs; BTC/ETH daily tops at PF 1.20 / Sharpe
  0.41 (vs the literature's idealized 2.45). Kept as a minor diversifier.
- **Dynamic funding rotation** (chase highest-funding perps): **worse than
  static** (−80%/yr at 2x) — funding is ~uniform (~10%/yr across pairs), so
  rotation adds only churn cost and buys crowded funding that reverts.
- **Static multi-pair funding carry (basis arb), 2x:** **+16.5%/yr full
  period at 0.81% max drawdown** — the most robust result across the entire
  research program.

**Conclusion:** the one arbitrage that genuinely works for this account is
**funding/basis carry**. Everything fancier (stat-arb, rotation, ML,
regime-switching) either helps at the margin or hurts. Compute is not the
bottleneck (the 190-pair scan runs in seconds); market efficiency is.
Deployable ARIES = static carry basket (core) + 4h crypto breakout basket
(satellite); scale returns with capital, not complexity.

## Grid trading battle-test (`ares/grid.py`)

Tested the "many micro-hits in a sideways market" idea on real ETH 15m:

- **Sideways 60-day window (1% drift): 1,367 round-trips, +6.1% (~37%/yr),
  5.2% DD.** In a genuine range, grid trading works exactly as hoped.
- **Full 18 months (trends + ranges), re-centered: -6.7%, 27% DD** — and
  identical with fees set to zero, so it's a TREND problem, not a cost
  problem. Trends leave the grid holding a losing bag that eats all the
  range profits. A naive range-break stop made it worse (-31%, churn).

Verdict: a legitimate range-harvester, but net profit depends entirely on
running it only during ranges and halting during trends -- and reliable
ahead-of-time regime detection is the same unsolved wall that sank the ADX
filter. Keep as an optional calm-market satellite with strict limits, never
core, and never leveraged (a leveraged grid bag is a liquidation).

## SOLVED: the hedged (delta-neutral) grid

The grid's fatal flaw was the directional bag in a trend. The fix is not to
predict the regime (that wall is real) but to **neutralise** it: grid-trade
long spot for the oscillation micro-profits while holding a short perp sized
to the inventory, so price direction cancels. Battle-tested on ETH/SOL 15m,
both 2024 and 2025 (`ares/grid.py::backtest_hedged_grid`):

| pair | 2024 | 2025 |
|------|------|------|
| ETH (ATR spacing) | +16.9%/yr, 2.6% DD | +10.0%/yr, 0.5% DD |
| SOL (ATR spacing) | +29.1%/yr, 4.1% DD | +14.0%/yr, 5.3% DD |

Positive and <6% drawdown in every slice -- the catastrophic 28-61% naive-grid
bag is gone. This is the user's grid idea + the carry's hedge principle: a
market-neutral volatility harvester that works across regimes.

Caveat: models a perfect hedge; real perp hedging adds basis tracking-error,
rebalance slippage, and negative-funding stretches, so live DD will be
somewhat higher -- but the directional catastrophe is genuinely removed.
Operationally heavier than plain carry (spot + perp + continuous rebalancing).

## Bottom line

Can ARIES "beat the market"? Not by prediction. But a disciplined
portfolio of real, cost-aware, validated edges — carry for stability,
higher-TF trend for growth, seasonality as a filter, ML only to sharpen —
is a credible, evidence-based path to positive expectancy with controlled
drawdown. The next concrete step is H1: does trend-following survive costs
on higher timeframes? That we can answer this week, on real data.


## Correction: the hedged grid was a phantom (supersedes all hedged-grid results)

Every "hedged grid" return previously recorded here was produced by a model
that booked the long leg's grid round trips but charged the short hedge only
fees, never marking the hedge's P&L. That violates the P&L identity
`price P&L = sum(position x dPrice)`: a delta-neutral book earns nothing from
price movement.

Proof (tests/test_grid.py::test_neutral_grid_cannot_harvest_oscillation): on a
pure sine wave with ZERO fees -- the most grid-friendly market possible -- a
fully hedged grid returns **-68%**, not a profit. The hedge is a mirror grid.

### What is actually real (corrected two-leg model, IS/OOS split)

Swept 21 prop-tradeable instruments (FX majors+crosses, metals, index futures,
energy, bonds, crypto) x hedge_ratio {0,0.3,0.5,0.7} x spacing {0.5-8 sigma} x
inventory {10,20,40}, config chosen on in-sample only:

- **Every market selected hedge_ratio = 0.0.** Hedging destroys the grid.
- FX majors: +0.0 to +1.5%/yr OOS at 0.3-1.6% DD. Edge is real and survives
  OOS, but it is microscopic -- hourly FX vol is too small vs capital.
- Index CFD/futures (US500/NAS100/US30/US2000): +5 to +11%/yr OOS, but
  **6.5-8.2% max DD** -- breaches a 6% prop-firm limit.
- Gold/Silver: IS +9.8/+16.7 -> OOS **-28.7/-52.9%** (26%/49% DD). Classic
  unhedged-grid trend death. Reject.
- WTI +7.2% OOS at 30.5% DD; COPPER +9.0% at 10.1% DD. Uninvestable.
- ETHUSDT 15m: +51.3% OOS at **39.4% DD**.

Nothing is simultaneously meaningful and inside a prop firm's drawdown limit.

### Market ranking metric (kept -- this part was sound)

For a diffusion, s-spacing crossings in time T scale as sigma^2*T/s^2, each
earning (s - c). Maximising `(sigma^2*T/s^2)(s-c)` gives **s\* = 2c** (which
independently validates min_edge_mult=2.0) and peak profit **∝ sigma^2/(4c)**.
Grid return scales with volatility SQUARED over cost. Measured sigma/cost:
WTI 15.4, Gold 13.8, Silver 10.6, NAS100 9.4, USDJPY 9.1 vs crypto perps 6.0 --
prop markets are 2x better on cost efficiency. That is true but insufficient:
a good sigma/c makes each hit profitable; absolute sigma decides whether the
total is worth anything, and FX's is not.

### Structural conclusion for the prop-firm goal

A neutral book pays only carry, and carry requires *two different* instruments
(so the legs' carries differ). Same-symbol long+short cancels it exactly --
which is why the all-perp "low-leverage futures" variant cannot work: it is
not that it loses half the return, it is that cancelling the carry leaves
nothing but fees.

The structurally sound carry source available inside ONE futures account is a
**calendar spread** (long near expiry / short far expiry): different
instruments, so the term-structure carry does NOT cancel, it is neutral to the
underlying's price, and futures prop firms support it with spread margin.
UNVALIDATED here -- it needs multi-expiry term-structure data, which the Yahoo
feed does not provide cleanly.

## Calendar-spread carry: VALIDATED AND REJECTED

The previous section named the futures calendar spread as the one structurally
sound carry source inside a single prop account, and flagged it unvalidated for
want of term-structure data. That data was found and the hypothesis was tested.

### Data

`scripts/fetch_term_structure.py` pulls EIA daily settlements for the nearest
four NYMEX contracts, keyless: WTI crude `RCLC1..4` (1985-2024, 9,158 rows) and
natural gas `RNGC1..4` (1994-2024, 7,149 rows). Yahoo is useless here -- dated
contracts (`CLZ25.NYM`) 404 once expired, so no history exists.

### Pre-specified hypothesis (not fitted)

With F(T) the price at time-to-maturity T: in backwardation F decreases in T, so
an ageing contract rolls UP, and the front leg -- steepest local slope -- rolls
fastest, so long-front/short-back gains. Contango reverses it. Hence
`position = sign(C1 - C2)`, fixed in advance.

### The trap this had to avoid

EIA C1..C4 are CONTINUOUS: at expiry C1 is relabelled and jumps by about
-(C1-C2), i.e. almost exactly MINUS the signal. Attributing P&L to that jump
manufactures an edge perfectly correlated with the signal. Measured: mean |daily
spread return| is 0.22% on normal days but 1.72% on day 20 of the month -- an 8x
spike across the CL roll window. Roll days are therefore taken from the
deterministic exchange expiry calendar (never from return size, which would be
snooping): 3.48x higher |r| on rule-flagged days, 21 of the 40 largest moves
flagged. A difference is treated as contaminated if EITHER endpoint is a roll
day -- excluding only the roll day itself leaks the jump into the next day's
diff, which alone was enough to turn a flat test panel into -99.98%/yr.
`tests/test_calspread.py` pins this: flat legs plus artificial roll jumps must
return EXACTLY zero fee-free.

### Result: the hypothesis fails

IS = first 60%, OOS = remainder (14yr for WTI, 11yr for NG). Cost 4bps
round-trip, conservative for CL at a prop firm.

| market | spread | IS ret | OOS ret | OOS Sharpe | OOS maxDD |
|---|---|---|---|---|---|
| WTI | C1-C2 | -2.28% | +1.72% | +0.15 | 25.7% |
| WTI | C1-C3 | +1.39% | +1.70% | +0.15 | 34.6% |
| WTI | C1-C4 | +4.73% | +1.60% | +0.15 | 38.0% |
| NG  | C1-C2 | -20.75% | **-7.33%** | -0.44 | 68.3% |
| NG  | C1-C4 | -25.67% | **-8.53%** | -0.37 | 77.2% |

Placebos (WTI OOS): inverted signal -16 to -19%/yr, random signal -10.3%/yr
(30 seeds, best -0.84%). So the WTI carry sign **does** carry real information --
it beats random by ~12pp/yr and inverting it loses systematically more than
random. That part of the theory is correct.

But it is unusable:
- WTI Sharpe +0.15 is noise-level, at 26-38% max drawdown. A 6% prop-firm
  drawdown limit is breached many times over.
- **Natural gas runs the hypothesis BACKWARDS** (OOS -7 to -9%; inverted is
  positive). NG term structure is dominated by winter/summer seasonality, so
  sign(slope) reads seasonality rather than carry. The a priori economics does
  not generalise across markets, and trading NG inverted would be fitting the
  market where the theory already failed.
- Sizing by carry magnitude instead of sign (pre-specified variant, one run, no
  search): WTI OOS improves to +5.26%/yr but Sharpe only +0.23 at 38% DD, and
  its IS turns negative -- IS/OOS disagree, so there is no stable edge.

**Verdict: rejected.** Real but noise-level information in WTI, sign-unstable
across markets, drawdown an order of magnitude past prop-firm limits. Nothing
here is tradeable, and no further tuning was attempted -- searching until a
number looks good is exactly what produced the phantom hedged grid.

## Time-series momentum: the first properly-powered test in this project

### The statistical correction that invalidates everything above

The standard error of a Sharpe ratio is `sqrt((1+S^2/2)/T)` where **T is elapsed
YEARS, not bar count**. Sharpe uncertainty is driven by uncertainty in the mean
return, which shrinks with calendar time, not sampling frequency. A year of
15-minute candles is exactly as uninformative about an edge as a year of daily
candles.

Consequence: every intraday result earlier in this document was underpowered by
construction, independent of the modelling bugs. The index-grid "Sharpe 0.77"
had a standard error of **+/-1.23** (95% CI [-1.64, +3.17], t=0.63) on 0.86
years of OOS data -- statistically indistinguishable from zero. Establishing
Sharpe 0.77 at t=2 needs ~6.8 years; we had 0.86. An 8x shortfall.

Corollary: **a 1.5-month paper run cannot validate anything** (SE ~ +/-2.9). It
verifies plumbing -- fills, hedge integrity, costs, uptime -- and nothing more.

### Method

`ares/ledger.py` (one audited P&L core, equity = cash + sum(position*price), no
code path that adds profit) + `ares/tsmom.py` (published Moskowitz/Ooi/Pedersen
rule: 12-month lookback, monthly rebalance, constant-vol sizing -- parameters
from the literature, nothing fitted) + `scripts/fetch_daily_history.py`
(20-57yr daily, 24 markets across equities/FX/commodities/rates).

Data-handling bugs found and fixed, each of which produced garbage:
- Yahoo `range=max` silently downgrades the interval (169 rows for 42yr of SPX);
  explicit period1/period2 is required.
- Yahoo stamps each market at its own local session time, so aligning on raw
  timestamps built a union index of 26,742 rows for 3 markets instead of
  ~14,000, forward-filling each across the others' stamps. The resulting runs of
  identical prices became zero-return days that collapsed the rolling vol and
  made 1/vol sizing explode (UST10 showed 0.4%/yr vol => 246x leverage).
  Normalising to the calendar date fixed it.
- The index is `datetime64[ms]`, not nanoseconds; dividing by 1e6 destroyed the
  time axis (56 years read as 0.02 days).

### Result

| window | Sharpe | t | note |
|---|---|---|---|
| 1970-2026 | +0.64 +/-0.15 | 4.34 | **confounded, see below** |
| **2000-2026 (full universe)** | **+0.42 +/-0.21** | **2.06** | the honest number |
| equities sleeve | +0.69 +/-0.15 | 4.62 | inflated by the same confound |
| FX sleeve | +0.12 +/-0.19 | 0.62 | not significant |
| commodities sleeve | +0.27 +/-0.20 | 1.35 | not significant |
| rates sleeve | +0.06 +/-0.20 | 0.29 | not significant |

The 56-year headline is **not** a clean diversified result. Risk is normalised
by `sqrt(24/n_live)` so aggregate risk stays constant as markets phase in, but
that gives the 1970s -- when only SPX had history -- 4.9x position size, so the
long sample is dominated by leveraged single-market S&P trend following. Adding
the 8 commodity markets changes the full-period figures not at all, which is the
tell. **Treat Sharpe ~0.42 (t=2.06, 26yr) as the estimate**, marginally
significant.

Placebos (full period): inverted signal reaches **ruin in 9.1 years**; random
signal -87.6%/yr, Sharpe -0.22 over 8 seeds. The signal direction is decisively
real. Costs: survives to 40bps round-trip (Sharpe 0.47 full / 0.42 at 10bps).

Sub-periods confirm the documented decay: 1990-2000 Sharpe 1.03, 2000-2010 0.62,
**2010-2020 Sharpe 0.04 at -1.08%/yr with a 53% drawdown**, 2020-2027 0.55.

### Known limitation, not yet addressed

Tested on cash indices and spot FX, not futures. For equities and FX the proxy
is defensible (financing roughly offsets). For **commodities it is materially
wrong** -- futures returns include roll yield that spot does not capture -- so
the commodity sleeve's +0.27 is not trustworthy. A proper test needs
roll-adjusted continuous futures.

### Prop-evaluation odds (10% target / 6% max DD, real TSMOM return shape)

10k Monte Carlo paths, 3-year cap, block-bootstrapped from modern-era daily
returns so fat tails and skew (-0.32) are preserved:

| assumed Sharpe | vol 3% | vol 6% | vol 10% |
|---|---|---|---|
| 0.64 (full-period) | 8% / 8% | 44% / **82%** | 37% / 63% |
| 0.30 (decay haircut) | 1% / 1% | 26% / 41% | 27% / 48% |
| 0.04 (2010s repeat) | 0% / 0% | 14% / 21% | 21% / 36% |

(trailing drawdown / static drawdown)

Two findings worth more than the strategy: **a static drawdown rule nearly
doubles the pass probability versus a trailing one at identical Sharpe** (82% vs
44%), and under a static rule ~6% vol beats 10%. Choosing the firm by its
drawdown mechanics matters more than improving the signal.

Unresolved and decisive before paying any fee: passing is not the goal,
surviving the funded account is. Modern DD/vol is ~2.8x, so a 6% ongoing limit
implies running at ~2% vol, i.e. ~1%/yr. Whether that is viable depends entirely
on whether the firm's loss floor LOCKS at breakeven once in profit. Verify that
before anything else.

## Quarterly-vs-perp carry: prop-compatible, and NEGATIVE since 2024

The structural problem with funding carry on a prop account is that it needs
long spot + short perp, and prop firms provide no spot. A dated (quarterly)
future pays no funding while a perp does, so **long quarterly + short perp** is
delta-neutral AND funding-collecting with both legs as derivatives in ONE
account. That solves prop-compatibility without spot.

Edge = annualised perp funding - annualised quarterly premium. (The quarterly's
own premium converges to zero by expiry, so holding it long is a cost.)

Measured over 44 dated Binance contracts, 2021-2026, BTC and ETH
(`scripts/fetch_quarterly.py`, `scripts/measure_quarterly_spread.py`).

**Partial data was misleading.** 2021-2022 alone read +5.91%; through 2023,
+4.51%. The full series reverses it. The edge has been negative for **eight
consecutive contracts in BOTH markets**, beginning at the same expiry:

| expiry | BTC edge | ETH edge |
|---|---|---|
| 240927 | -4.58% | -3.28% |
| 241227 | -3.45% | -1.71% |
| 250328 | -1.80% | -0.86% |
| 250627 | -2.94% | -2.43% |
| 250926 | -1.41% | -1.04% |
| 251226 | -0.96% | -0.90% |
| 260327 | -2.11% | -1.91% |
| 260626 | -1.90% | -2.23% |
| **mean** | **-2.39%** | **-1.80%** |

Two independent markets flipping at the same contract is structural, not noise,
and the cause is identifiable: spot Bitcoin ETFs launched in January 2024 and
brought institutional basis-trade demand, bidding dated-futures premiums up
relative to perp funding. The quarterly premium now exceeds the funding, so the
trade pays out more than it collects.

The headline means (+1.73% BTC, +2.85% ETH) are entirely driven by 2021-2024
and must NOT be read as a forward expectation. Forward expectation is about
-2%/yr before fees. **Rejected.**

Economic reason it was always going to be thin: perp funding and dated basis
both price the same leveraged-long demand, so they track closely and their
spread is only a residual. Plain spot+perp collects the FULL funding (+4.32%/yr
in 2022) where quarterly+perp collects only the gap (+1.35%).

## The prop-account survival problem: solved for survival, capped for earning

Sizing risk in proportion to the distance from the account's kill line
(`scripts/test_floor_sizing.py`) removes ruin entirely -- 0 deaths in 4,000
bootstrapped 3-year paths at k<=1.0, while still touching a 10% profit target
56% of the time. But it does not create return: a loss shrinks position size,
which slows recovery, so survival is paid for out of the return (median falls
to ~0%/yr).

The cap is arithmetic, and simulation matches it:

    sustainable return ~= edge_quality * room / bad_streak_multiple
                        = 0.49 * 6% / 2.5 = 1.2%/yr

against 1.15% measured at the size where only 0.4% of accounts die. Earning
10%/yr under a 6% rule would require Sharpe ~4; nothing directional reaches
that, and the only thing measured here that does is market-neutral carry
(~3.5), which needs the spot leg prop firms do not offer. That is the whole
reason the constraint binds.

**Percentage is the wrong unit.** 1.2%/yr is near-useless as a rate but the
dollars follow the capital: at the safe size, roughly $265/yr on a $25k
account, $441 on $50k, $882 on $150k and $1,323 on $300k after a 90% split --
against $9.80/yr from trading $50 of own capital at full risk (19.6%/yr, a far
better rate, 50-130x less money).

**Unresolved and decisive:** prop account fees run roughly $85-105/month, i.e.
$1,000-1,200/yr, which EXCEEDS the earnings on a $25k or $50k account. This is
only viable on a larger account and only if the fee is a one-time activation
rather than recurring. Verify the fee schedule before buying anything.

## Fast strategies: why everything here was slow, and what the speed limit is

### The diagnosis

Strategy quality = (edge per bet) x sqrt(bets per year). Trend following makes
~25 bets/yr, so sqrt(25)=5 caps its quality near 0.5 regardless of tuning --
exactly the 0.49 measured after seven enhancement attempts. Earning real money
inside a 6% account drawdown limit needs quality ~4. On that formula the lever
is BET COUNT, not better prediction: at 10,000 bets/yr, sqrt(N)=100 and a
per-bet edge twenty times smaller suffices. Most of this project searched the
wrong axis.

### The test

`ares/xsreversal.py`: cross-sectional short-term reversal across 25 liquid USDT
pairs, 5.7yr hourly (50,362 bars). Strip the common market factor by demeaning
returns across the universe, then short the assets that diverged upward and buy
those that diverged downward, equal dollars, market-neutral. ~8,764 bets/yr.

**The signal is real and large.** Gross, before costs: +547.9%/yr at
hourly rebalance, +173.5% at a 4-hour lookback, +74.8% holding 4 hours. Not
noise -- validated first on synthetic data where reverting idiosyncratic moves
profit, trending ones reach ruin, and a random walk is indistinguishable from
zero (mean Sharpe +0.157 over 12 seeds).

### The speed limit: it lives entirely inside the fee structure

Turnover is ~155% of equity per rebalance, so hourly trading turns over ~13,760x
capital per year. Per bet the edge is **2.13bp of equity** while a 2bp
round-trip fee costs **3.14bp**. Cost exceeds edge, so:

| look | hold | gross %/yr | edge/bet | breakeven | net @2bp |
|---|---|---|---|---|---|
| 1 | 1 | +547.9% | 2.13bp | **1.36bp** | **-58.4%** |
| 1 | 4 | +74.8% | 2.55bp | **1.64bp** | -11.2% |
| 4 | 1 | +173.5% | 1.15bp | 1.38bp | -36.6% |
| 4 | 4 | +28.3% | 1.14bp | 0.73bp | -35.2% |
| 4 | 72 | +0.3% | 0.25bp | 0.16bp | -3.5% |

**Every configuration is negative at 2bp.** Best breakeven is 1.64bp round-trip,
against ~15bp for retail Binance spot maker (7.5bp a side with BNB discount) and
~2.4bp at the top VIP tier. So the edge is roughly **10x too small for retail
fees and still short of the best published tier.** It is real, and it belongs to
whoever trades at or below ~1.6bp -- i.e. firms with rebates. That is a concrete
explanation of why this game is not retail-accessible, rather than a vibe.

Longer holds cut the fee bill but cut sqrt(bets) faster: by hold=12 the gross
edge is already negative, so there is no slow-enough version that survives.

### Four harness bugs, all caught by impossible output rather than wrong-looking output

Worth recording because the pattern repeated:
1. Market-neutral books at **-100% with zero fees** -- positions sized off
   starting capital, so leverage grew as equity fell.
2. **"2 bets/yr"** for a hold=72 config -- returns annualised over the full
   5.7yr even when the book died in month three.
3. **1,156,298% turnover** per rebalance -- raw notional over STARTING capital
   once the book compounded, which silently zeroed the breakeven.
4. **Breakeven overstated ~3x** (3.99bp vs a true 1.36bp) -- a COMPOUNDED
   annual rate divided by SIMPLE annual turnover, which labelled as "tradeable
   at maker" a configuration whose own net column read -58.4%/yr.

Bug 3 printed +547.9%/yr next to the broken turnover; bug 4 then dressed it as
tradeable. Reading the return column alone would have shipped it.
`tests/test_xsreversal.py` now asserts that trading AT the breakeven cost leaves
roughly nothing -- the consistency check that would have caught bug 4 at once.

## Fixing the fee wall: the instrument, not the strategy

The crypto reversal edge was real (gross +74.8%/yr at a 4-hour hold) but its
breakeven was 1.65bp round-trip against ~15bp retail Binance spot -- about 10x
too expensive. Two fixes were tried.

### Selectivity: fails, and the failure is informative

Trading only dislocations beyond N sigma leaves the fee unchanged while raising
the edge per bet, so it should help. It does the opposite:

| threshold | gross %/yr | bets/yr | breakeven |
|---|---|---|---|
| none | +74.8% | 2,191 | 1.65bp |
| 1 sigma | +39.7% | 2,095 | 1.00bp |
| **2 sigma** | **-9.1%** | 923 | **-0.89bp** |
| 3 sigma | -10.2% | 283 | -3.60bp |

The edge turns NEGATIVE by 2 sigma. Large crypto dislocations are news -- hacks,
listings, liquidation cascades -- and news does not revert; it is real
repricing. **The edge is small precisely because it is noise-driven, so
anything big enough to pay a 15bp fee is news.** Structural, not tunable.

### Changing instrument: this is the fix

Cost per unit notional is set by contract size, and futures are enormous
relative to their commission:

| instrument | round-trip cost |
|---|---|
| Binance spot (retail maker) | 15.00 bp |
| MES micro S&P ($30k notional) | 0.75 bp |
| MNQ micro Nasdaq ($44k) | 0.34 bp |
| MGC micro gold ($40k) | 0.50 bp |

20-40x cheaper. A 1.65bp breakeven fails at 15bp and clears at 0.75bp. These
are also precisely the instruments a futures prop firm offers, so the fix and
the account type coincide.

### Result on 22 futures, hourly, 2.4yr (`scripts/fetch_futures_intraday.py`)

Data hazards found and handled before trusting anything. Yahoo's continuous
front-month series carry ROLL DISCONTINUITIES: natural gas showed a 27.08%
single-hour move (27 sd), silver 19.92%, copper 17.13%, and the >10sd counts
cluster in energy (HO 21, RB 20, NG 11) -- the same group that produced the
largest apparent edge. Bars beyond 5%/hour and their neighbours are blanked,
since a reversal strategy profits from both the glitch and its mirror image.
Zero-volume (stale) bars are only ~4%, and grains simply have fewer bars rather
than filled ones, which the live mask already handles.

| universe | in-sample | out-of-sample |
|---|---|---|
| energy (CL/NG/RB/HO) | +66.4%/yr, Sharpe 2.07 | **-41.4%/yr, Sharpe -1.20** |
| **ALL 22** | +38.5%/yr, Sharpe 3.67 | **+22.7%/yr, Sharpe 1.80 +/-1.48** |

Energy was pure overfit: best-of-nine configurations chosen in-sample, and it
collapsed out-of-sample. Rejected.

The broad 22-market version survived, degraded, at **+22.7%/yr net of 0.75bp
costs, Sharpe 1.80 +/-1.48, maxDD 19.4%**, with profit not pathologically
concentrated (top 1% of bars carry 8% of absolute movement).

**What is established:** the fee wall is fixed by the instrument. The same
strategy family goes from every configuration negative on crypto spot at 15bp
to +22.7% out-of-sample on futures at 0.75bp.

**What is NOT established:** the edge itself. 1.2 years out-of-sample gives a
Sharpe standard error of +/-1.48, so t = 1.22 -- not significant. The 95%
interval spans [-1.1, +4.7]. This is a promising lead, not a finding.

### Why it matters if it holds

Sharpe 1.80 with DD/vol of 1.54x is a different animal from trend following
(0.49 at 2.5x). Under a 6% account kill line the safe size is 3.9% vol, giving
**7.0%/yr** rather than 1.2%:

| account | %/yr | gross $/yr | keep 90% |
|---|---|---|---|
| $50,000 | 7.0% | $3,510 | $3,159 |
| $150,000 | 7.0% | $10,531 | $9,478 |
| $300,000 | 7.0% | $21,062 | $18,956 |

against $265-1,323/yr for trend following. The blocker is data: Yahoo caps
hourly history at 730 days, and confirming a Sharpe near 1.8 to t=2 needs
roughly 5 years of out-of-sample hourly futures data.

## Independent confirmation: reversal is real, measured over 57 years

The hourly futures result (Sharpe 1.80 OOS) rested on 1.2 years and was not
significant (t=1.22). The same idea run DAILY on the 57-market daily panel over
57 years gives a properly powered read, on data independent of the hourly tests.
Implausible daily moves (>25%) and their neighbours are blanked first, since
continuous front-month series carry roll discontinuities.

| look | hold | cost | return %/yr | Sharpe | t | maxDD |
|---|---|---|---|---|---|---|
| 1 | 1 | 0.00bp | +5.67% | +0.79 +/-0.15 | **5.22** | 31.0% |
| 1 | 1 | 0.75bp | +3.38% | **+0.49 +/-0.14** | **3.50** | 34.9% |
| 2 | 1 | 0.75bp | +2.54% | +0.36 | 2.59 | 38.1% |
| 5 | 5 | 0.75bp | +0.48% | +0.09 | 0.71 | 48.0% |

**t = 3.50 after realistic futures costs, over 57 years.** Cross-sectional
reversal is a real, persistent phenomenon in futures, not an artifact of a short
crypto sample. This is the first properly significant strategy result in the
repo besides funding carry.

### The speed theory predicts the hourly number

Sharpe = (edge per bet) x sqrt(bets per year). From the daily result:
edge per bet = 0.49 / sqrt(252) = 0.0309. Scaling to hourly:

    predicted hourly Sharpe = 0.0309 * sqrt(8760) = 2.89
    observed hourly OOS                           = 1.80

Same order of magnitude, observed below predicted -- which is what should
happen, since per-bet edge decays as frequency rises and fees bite harder. Two
independent datasets agreeing quantitatively is the strongest evidence produced
in this project.

### What is still NOT established, and the blocker

The daily version is significant but NOT prop-viable: maxDD 34.9% against vol
~6.9% is a DD/vol of ~4.5x, so a 6% kill line permits only ~1.3% vol and
~0.65%/yr. The HOURLY version is the one with a usable DD/vol (1.54x, giving
7.0%/yr under a 6% line), and that one has only 1.2 years out-of-sample.

Confirming Sharpe ~1.8 to t=2 needs roughly 5 years of out-of-sample hourly
futures data. Sources checked in this environment:

- **Yahoo**: works but hard-capped at 730 days of hourly (2.4yr). Already used.
- **Stooq**: the agent proxy terminates the connection mid-transfer
  (`ws_closed_mid_exchange`); unusable here.
- **Dukascopy freeserv**: returns `_callbacks____error([null])` even for
  EUR/USD; the per-day binary datafeed would need ~25,000 requests for 5yr x 20
  instruments, impractical.
- **Databento / TwelveData / Polygon / EODHD**: HTTP 401 -- all require an API
  key. **Databento is the right one**: purpose-built for CME historical, data
  from 2010, and $125 of free signup credit, which covers 5-10yr of hourly bars
  for ~20 instruments many times over.

So the remaining step needs a user-supplied Databento API key. Everything else
is built: `ares/xsreversal.py` on the audited ledger, roll-gap cleaning, an
in-sample/out-of-sample harness, and the breakeven-cost metric.

## Venue choice: cost dominates the drawdown leash

A firm with a 10% max drawdown instead of 5% doubles the extractable return at a
given Sharpe, so a wider leash looked like the best available lever. Searching
for one changes the answer: **every firm offering a 10% leash is a CFD firm**
(FTMO 10% static from initial balance with a 5% daily limit, The5ers 10%/4%,
FundedNext 10%/5%), and CFD spreads destroy this strategy outright.

Same strategy, same out-of-sample window, only the cost changed:

| venue | round-trip cost | OOS return | Sharpe | DD/vol |
|---|---|---|---|---|
| CME micro Nasdaq (MNQ) | 0.34bp | **+43.6%** | **+3.11** | 0.88 |
| CME micro S&P (MES) | 0.75bp | +22.7% | +1.80 | 1.06 |
| CFD EURUSD-like | 1.67bp | **-13.9%** | -1.16 | 1.96 |
| CFD gold-like | 2.17bp | **-29.0%** | -2.79 | 2.48 |
| CFD index-like (US500) | 3.20bp | **-52.2%** | -6.15 | 3.35 |

Resulting prop economics:

| venue | leash | safe vol | %/yr | %/month | $/mo on $50k |
|---|---|---|---|---|---|
| MNQ futures | 5% | 5.65% | 17.56% | **1.36%** | **$658** |
| MES futures | 5% | 4.73% | 8.49% | 0.68% | $318 |
| any CFD firm | 10% | -- | LOSES | -- | -- |

**A 10% leash on an edge that has gone negative is worth nothing.** Halving the
cost from 0.75bp to 0.34bp roughly DOUBLED the return, so the venue criterion is
the lowest commission on micro futures, not the widest drawdown allowance. That
favours the cheap-CME-micro firms (Apex, Topstep, MyFundedFutures, Tradeify)
over the 10%-leash CFD firms, and it corrects the earlier conclusion that a
wider leash was the biggest available lever.

Caveats: these are 1.2yr out-of-sample figures with wide error bars, so the
LEVELS are provisional (the 15yr Databento pull settles them). The RELATIVE
cost comparison is robust, since it is the same data at different cost
assumptions. Also note For Traders offers 10%/5% on some futures accounts but
states HFT is not permitted, and an hourly-rebalanced book making ~8,760 trades
a year may attract that scrutiny even though it is not HFT in the sub-second
sense -- worth confirming with any firm before paying.

## "Train it to cut losing bags" -- already tested, and it backfires

Adding an exit rule (stand aside while price is below an EMA) to the directional
grid was worse in ALL 20 pair/length/split combinations, e.g. ETH +4.41% ->
-14.02%. The mechanism: cutting the bag crystallises the loss and then sits out
the recovery, and the recovery IS the edge.

More to the point, the cross-sectional construction removes the problem rather
than managing it. There is no directional bag to accumulate because the book is
simultaneously long the laggards and short the leaders. The thing a smarter exit
would be trained to avoid does not arise.

Measured priority therefore favours cost (0.34bp vs 0.75bp roughly doubles the
return) over learned exits (which made the comparable strategy 3x worse).

## VERDICT on hourly cross-sectional reversal: rejected on 15 years of CME data

The hourly result that drove the whole fast-strategy phase (Sharpe 1.80, later
3.11 at MNQ costs) came from 2.4 years of Yahoo futures data with a 1.2-year
out-of-sample window. Databento's CME `ohlcv-1h` settles it: 20 continuous
contracts, 1,363,034 bars, 2011-2025, for $8.85 of the free credit.

Coverage screen first: metals map poorly to hourly in this dataset (PL 4.3
bars/trading-day, SI 5.9, HG 8.5, GC 9.2 against 19.1 for ES/NQ), so they were
dropped as stale-price contaminators, leaving 16 markets at 15.7-19.1 bars/day.
Roll gaps and bad ticks (>5%/hour) and their neighbours blanked. Config chosen
in-sample only, 9yr in-sample / 6yr out-of-sample.

| venue | in-sample (9yr) | out-of-sample (6yr) |
|---|---|---|
| MNQ @ 0.34bp | +4.79%/yr, Sharpe +0.68 | **+2.63%/yr, Sharpe +0.32 +/-0.42, t=0.76** |
| MES @ 0.75bp | -3.20%/yr, Sharpe -0.38 | **-9.00%/yr, Sharpe -0.78, maxDD 52.1%** |

At the realistic cost it LOSES. At the optimistic cost it is indistinguishable
from zero. On a $50k account under a 5% leash this is **$18/month**, against the
$658/month projected from the short Yahoo sample.

Cause of the earlier overestimate: 1.2 years out-of-sample, best-of-nine config
selection, and Yahoo hourly futures data carrying quality defects already
documented here (a 27.08% single-hour move in natural gas). Short sample plus
noisy data plus selection.

### The speed thesis is dead, and this is why

The whole phase rested on quality = (edge per bet) x sqrt(bets per year), which
predicted that moving from daily (Sharpe 0.49 over 57 years, t=3.50 -- that
result stands) to hourly should give:

    predicted hourly Sharpe = (0.49/sqrt(252)) * sqrt(8760) = 2.89
    measured on 15yr CME     = 0.32

**Speeding up does not multiply the edge.** sqrt(N) assumes a constant per-bet
edge; in reality the per-bet edge decays faster than sqrt(N) grows, because at
higher frequency an increasing share of apparent "dislocation" is bid-ask bounce
and microstructure noise that cannot be captured. This also explains why the
crypto version needed a round-trip cost below 1.6bp that does not exist at
retail: there was less real signal there than the gross figures suggested.

### What survives, after nine strategy families

- **Funding carry** (long spot + short perp): ~17-20%/yr at moderate leverage on
  own capital, maxDD ~1-2%. Real, validated on 6.7yr of actual funding history,
  not prop-compatible (needs spot).
- **Daily cross-sectional reversal**: Sharpe 0.49 after costs, t=3.50, 57 years.
  Real and significant, but DD/vol ~4.5x makes it worth ~0.65%/yr under a 5%
  prop leash.

Rejected: hedged grid (accounting identity), all-perp futures carry (funding
cancels), crude/natgas calendar spreads (Sharpe 0.15, sign-unstable), quarterly
vs perp (negative since the 2024 ETF launch), directional grid (dominated by
carry), crypto hourly reversal (fee-bound below 1.6bp), hourly futures reversal
(this section).

### Regime check: the edge decayed, and recent data is the WORSE data

Tested directly on the claim that only recent conditions matter. Same config,
MNQ cost 0.34bp, by era, on the 15yr CME panel:

| era | return/yr | Sharpe | t | maxDD |
|---|---|---|---|---|
| 2011-2013 | +14.09% | **+1.99** | 2.00 | 14.8% |
| 2014-2016 | +9.75% | +1.14 | 1.53 | 14.5% |
| 2017-2019 | -0.38% | -0.00 | 0.00 | 22.2% |
| 2020-2022 | +1.13% | +0.19 | 0.32 | 27.8% |
| 2023-2025 | +4.67% | +0.56 | 0.90 | 15.9% |
| 2025 only | +2.35% | +0.31 | 0.30 | 14.6% |

The edge was genuinely strong in 2011-2016 (Sharpe 1.99 then 1.14) and has been
at or near zero since 2017. **Discarding history would not have helped: the
recent sample is the weaker one.** A 2025-only test finds Sharpe 0.31 and
nothing to build on.

This is decay by competition. In 2011 hourly cross-market reversal was awkward
to automate and lightly traded; by 2017 it was crowded and the edge had been
competed down toward the fee floor. The full-sample Sharpe 0.32 is the average
of a dead recent regime and a live old one, and the 15yr rejection stands.

Best case from the most recent era: Sharpe 0.56 at maxDD 15.9% is DD/vol ~1.9x,
so a 5% prop leash permits ~2.6% vol and ~1.5%/yr -- about $61/month on $50k.

**Strategic implication worth more than the result:** the decay curve says edges
live where automation has not yet arrived. Futures hourly reversal paid in 2011
and does not now; crypto funding carry paid 27-37%/yr in 2020-21 and pays 2-5%
now (measured earlier in this document). Both decayed as participants arrived.
That argues for newer or less-contested venues rather than better signals in
mature ones -- but prop firms offer only the mature venues, which is the bind.
