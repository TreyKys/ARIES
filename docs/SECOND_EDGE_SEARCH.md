# The search for a second, uncorrelated edge

**Verdict: no second edge found. Nine candidates tested across two slates;
only the reversal leg the book already has carries any edge. But the search
found something worth more than an addition would have been — the book's
trend leg is drag, and removing it lifts Sharpe from 0.47 to 0.69 at a
$100,000 account.**

Measured 2026-10-09/10. `ares/edges.py`, `scripts/find_second_edge.py`,
`scripts/risk_transfer_edges.py`.

---

## 1. First, how much is needed

Independent edges combine as `S_total = sqrt(sum of S_i²)`. From 0.54, one
addition reaching 1.2 would itself need **Sharpe 1.07** — larger than anything
in this repo and larger than most documented factors survive out of sample.
Stacking equal edges of 0.54 gives 0.76 for two, 0.94 for three, 1.21 for
five.

So the target was never "find an edge". It was "find four". That framing
should have been stated before the search began, and it sets how to read
everything below.

One consolation: a *negatively* correlated pair does better than an
independent one. Two 0.54 edges at r = −0.3 combine to 0.91. Value, which is
negatively correlated with momentum by construction, was the most interesting
candidate for exactly that reason.

## 2. Slate 1 — seven standard price-based factors

Each written to its published specification in `ares/edges.py` and committed
before measurement. All run through the same sizing, cost and ledger path, so
the correlations between them are real and not harness artifacts. Eight
tradeable markets, 2006–2026 (a six-year warmup is forced by value's
five-year lookback), $1M uncapped.

| edge | source | Sharpe | t | IS | OOS |
|---|---|---|---|---|---|
| **xsrev** (1-day cross-sectional reversal) | Lehmann 1990 | **+0.94** | +3.75 | +0.96 | +0.91 |
| trend (12-month time-series momentum) | Moskowitz+ 2012 | +0.14 | +0.67 | +0.28 | −0.01 |
| skew (lottery preference) | Bali+ 2011 | +0.12 | +0.57 | +0.04 | +0.19 |
| xsmom (12-1 cross-sectional momentum) | Jegadeesh+ 1993 | +0.11 | +0.53 | +0.19 | +0.03 |
| tsrev (1-month own reversal) | — | +0.07 | +0.35 | +0.16 | −0.02 |
| seasonal (same-month history) | Heston+ 2008 | +0.00 | +0.01 | −0.07 | +0.08 |
| lowvol (betting against beta) | Frazzini+ 2014 | −0.13 | −0.64 | −0.12 | −0.15 |
| value (5-year reversal, skip 1yr) | Asness+ 2013 | −0.21 | −0.99 | −0.13 | −0.29 |

**Every single candidate reduces the combined Sharpe when added to xsrev**
(best case skew: 0.94 → 0.75). Not one earns its place.

Crucially, independence was *not* the problem. xsrev correlates with every
other candidate at |r| ≤ 0.28 — it is already its own thing. There was simply
no edge on the other side to combine with.

## 3. Slate 2 — risk transfer, not price patterns

Slate 1's result reframes the search. Reversal is not a forecast; it is a
**liquidity-provision premium**, payment for absorbing someone's urgent order
flow. So the natural second edge is another form of paid risk transfer.

**Overnight effect** (Cooper/Cliff/Gulen; Lou/Polk/Skouras 2019) — holding
through a closed market is unhedgeable gap risk, and a time-of-day exposure
cannot correlate with a cross-sectional bet by construction. Measured on
hourly data, 2011–2025, with regular hours taken as 14:00–21:00 UTC from the
volume profile:

| | night %/yr | day %/yr |
|---|---|---|
| ES | +5.78% (t=1.85) | +6.84% (t=2.33) |
| NQ | +9.50% (t=2.55) | +8.56% (t=2.39) |
| CL | −1.89% | +7.04% |
| 6E | −1.80% | +1.31% |
| **equal-weight basket** | **+0.70%/yr, Sharpe +0.06 (t=0.20)** | +4.61%/yr |

The equity indices do earn overnight — but they earn just as much by day, and
commodities and FX are negative at night. The classic finding is a *cash
equities* effect where the open gap captures it; index futures trade nearly
around the clock, so the mechanism barely applies. No edge.

**Turn of the month** (Ariel 1987; Lakonishok & Smidt 1988): +4.04 bp/day
inside the window against +3.88 bp/day outside it. A difference of **0.16
bp/day**. Nothing.

## 4. What the search actually found

Sharpe is **monotonically decreasing** in the weight given to the trend leg:

| w_trend | Sharpe | IS | OOS | maxDD |
|---|---|---|---|---|
| **0.00 — reversal only** | **+0.94** | +0.96 | +0.91 | 19.6% |
| 0.25 | +0.87 | +0.97 | +0.77 | **13.7%** |
| 0.50 — what the runner does today | +0.64 | +0.80 | +0.48 | 15.6% |
| 0.75 | +0.32 | +0.47 | +0.16 | 18.6% |
| 1.00 — trend only | +0.14 | +0.28 | −0.01 | 31.1% |

At real account sizes, with whole contracts and the 3-contract cap:

| capital | w=0.50 (now) | w=0.00 |
|---|---|---|
| $25,000 | 0.61 | **0.95** |
| $50,000 | 0.53 | **0.74** |
| $100,000 | 0.47 | **0.69** |
| $150,000 | 0.46 | **0.69** |

That is a larger improvement than any realistic addition would have produced.

**The crisis-alpha defence of trend does not survive the data.** Trend is
supposed to earn when markets break. In five of six stress years reversal-only
*beat* the blend — 2011 (+41.5% vs +26.6%), 2015 (+2.3% vs −3.0%), 2018
(+21.0% vs +9.8%), 2020 (+22.4% vs +14.9%), 2022 (+24.0% vs +15.5%). Only
2008 favoured keeping trend (+8.4% vs +11.7%). Negative years are 7/24 either
way.

### The honest caveat

Dropping trend is a decision made on ~20 years of modern data against a
57-year prior in which the trend leg scored 0.70. Two things support acting
on it anyway: the relationship is monotonic rather than noisy, which is the
signature of adding a zero-edge leg that still costs money; and two
independent measurements on different windows agree (0.14 here, 0.11 over
2000–2026). But it is still the recent era outvoting the long one.

Note also that `top_k=2` scored higher than `top_k=3` (1.09 vs 0.94). That is
**not** being adopted — switching a parameter because it scored better on the
same data is the exact mistake this document is trying to avoid.

## 5. Effect on the prop question

Re-running the Phidias Premium simulation with the reversal-only book
(replay Sharpe 0.41 → 0.57):

| | current book | reversal only |
|---|---|---|
| EV per attempt | ~$400 | **~$650** |
| best $/month | $241 | $291 |
| pass rate | ~31% | ~32% |

Better, and still not enough. The pass rate barely moves because the 2:1
evaluation gate dominates everything until Sharpe approaches 1.2.

## 6. Where this leaves it

Three routes out of docs/PROP_FIRMS.md are now closed by measurement:
breadth, speed, and a second edge. The fourth — stacking *four or five*
independent edges — is not a research project with a deadline; the honest
reading of slate 1 is that on eight liquid futures at a daily horizon, there
is one edge, and we are already trading it.

What remains worth doing, in order:

1. **Drop or reduce the trend leg.** Already available: `--strategy reversal`
   sets w_trend to 0. The largest single improvement found in this whole
   search, and it costs nothing to adopt.
2. **Run the paper phase.** Sharpe ~0.7 at $100k on own capital is a real
   strategy; it is simply not a prop-gate-clearing one.
3. **Carry, if the data is ever bought.** The one classic factor that could
   NOT be tested here: the term-structure signal needs front and second
   contract prices for all eight markets, and only crude and natural gas are
   on disk. It is the most-documented factor missing from slate 1 and the
   only remaining candidate with a strong prior.
