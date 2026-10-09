# Widening the universe: tested, and it does not work

**Verdict: adding every tradeable CME micro contract does not raise Sharpe.
The added markets have no edge of their own, so breadth dilutes instead of
diversifying. The existing 8 markets remain the best book in this repo.**

Measured 2026-10-09 with `scripts/widen_universe.py`.

---

## Why it was worth trying

The prop-firm gate needs about Sharpe 1.2 (docs/PROP_FIRMS.md). Breadth was
the one lever with a theoretical reason to work and no fitted parameter: for
N streams with *independent edge*, portfolio Sharpe scales with sqrt(N).

That conditional clause turns out to be the whole story.

## The tiers, committed in advance

Each tier is a RULE, not a selection — "every remaining CME-group micro", "the
mini grains", "the micro crypto" — and every tier is reported whether it
helped or not. Searching over subsets of 19 markets would have found a
beautiful backtest and nothing else.

Measured over one common window (2000-08-30 to 2026-10-07) so the tiers are
comparable, at $1,000,000 with the per-market cap lifted so granularity does
not bind, `top_k` scaled with universe size:

| tier | N | return/yr | Sharpe | IS | OOS | maxDD |
|---|---|---|---|---|---|---|
| **T1 current 8** | 8 | +5.44% | **+0.54** | +0.59 | **+0.48** | 26.7% |
| T2 + CME micros (M2K MHG MNG M6B MJY MCD) | 14 | +4.70% | +0.48 | +0.68 | +0.27 | 24.2% |
| T3 + mini grains (XC XW XK) | 17 | +3.96% | +0.41 | +0.72 | +0.08 | 31.1% |
| T4 + micro crypto (MBT MET) | 19 | +5.81% | +0.48 | +0.73 | +0.21 | 23.5% |
| **ADDED only** | 11 | +1.13% | **+0.13** | +0.28 | **−0.03** | 19.9% |
| ALL in data/daily (research only, untradeable) | 63 | −13.52% | −0.26 | −0.06 | −0.47 | 98.3% |

The decisive row is **ADDED only**: the eleven new markets traded as their own
book measure Sharpe +0.13 ± 0.20, t = 0.66, out-of-sample −0.03. They carry no
edge. Adding them to a book that does have one can only dilute it, and that is
exactly what the tier rows show.

Note also the IS/OOS split widening as the universe grows (+0.59/+0.48 at T1
versus +0.73/+0.21 at T4). More markets give the cross-sectional ranking more
room to look good in-sample and less out of it.

And the decade pattern. T1: **+0.19 / +0.59 / +0.88** across the 2000s, 2010s
and 2020s — improving. ADDED only: +0.24 / +0.10 / +0.05 — decaying to
nothing. Whatever these markets once offered is gone.

## Two things found while testing, one of them a real bug

**A confound in the first run, which would have produced a wrong answer.**
The reversal leg trades `top_k` longs and `top_k` shorts regardless of how
many markets exist, while the trend leg takes a position in every market. With
`top_k` fixed at 3, growing the universe silently shifts the book away from
reversal and towards trend — a change of strategy, not a test of breadth. The
first run showed Sharpe collapsing 0.54 → 0.21 → 0.02; scaling `top_k` with N
recovered nearly all of it (0.54 → 0.48 → 0.41). The real effect of breadth is
roughly flat, not catastrophic, and reporting the first run would have been
wrong.

**A latent bug in live sizing.** Position size is inversely proportional to a
market's volatility estimate, and `size_positions` only guarded against
exactly zero. A collapsed estimate — a halted market, a holiday, a run of
forward-filled prices — therefore asks for an unbounded position. With the
per-market contract cap lifted, one stale series took the 63-market book to
**970% volatility and total ruin**. The cap normally hides this, which is
precisely what makes it dangerous: it stays invisible until someone raises the
cap for a larger account. Fixed by flooring each estimate at 25% of the median
across live markets, which costs nothing on healthy data (0.54 → 0.54 on 8
markets, 0.47 → 0.48 on 19) and is pinned by three tests.

A third idea failed honestly: ranking the reversal leg on volatility-
normalised moves rather than raw ones, so that natural gas (>5% on 13.7% of
days) and ether (18.2%) stop monopolising the extremes. It works as intended
on synthetic data but changed real results by less than 0.01, because
`size_positions` already scales positions by inverse volatility — the risk was
normalised downstream all along. Kept as an option, defaulted off.

## A correction to something this repo has been claiming

`docs/STRATEGY_RESEARCH.md` reports the combined book at **Sharpe 0.84, t=5.37
over 57 years**, and that number has been cited here as evidence that breadth
would close the gap. Decomposed, it does not support that:

- It was measured on a **57-market panel over 57 years**, most of it
  untradeable at micro size by a small account.
- Its trend leg scored **0.70** there. Measured on tradeable markets over
  2000–2026, the trend leg scores **+0.11, out-of-sample +0.00**.
- The entire modern edge is the reversal leg.

So 0.84 is substantially an artifact of an era in which trend-following
worked. It is not a target reachable today by adding markets, and it should
not be quoted as one.

## What a real account actually gets

Whole contracts, 3-contract per-market cap, same window:

| universe | $25k | $50k | $100k | $150k |
|---|---|---|---|---|
| 8 markets | 0.56 | 0.43 | 0.38 | 0.38 |
| 14 markets | 0.38 | 0.40 | 0.43 | 0.36 |

Every figure sits within one standard error (±0.21) of every other. At the
$100,000 size of a Phidias Premium account the book delivers roughly **Sharpe
0.4 against the 1.2 the gate needs**. Breadth does not close that.

## What this leaves

Breadth is exhausted as a lever, and the way it failed is informative: the
limit is not how many markets the book trades but how many markets still
*have* a short-horizon reversal edge. On this evidence that set is small, it
is the one already being traded, and it is not obviously shrinking — T1's
best decade is the current one.

Routes not yet tested, in the order their odds look best:
1. **A second uncorrelated edge** rather than more markets for the same one.
   The 0.84 result worked because trend and reversal correlated +0.007; the
   gain came from independence, not from breadth.
2. **Intraday reversal on the 8 markets that do work** — tested once on hourly
   data and rejected (OOS Sharpe 0.32, t=0.76), but that test used all 16
   markets rather than the 8 with a measured edge.
3. **Accept Sharpe 0.4** and run it on own capital at a broker, where there is
   no 2:1 gate to clear.
