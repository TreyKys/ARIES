# Hourly reversal, re-tested on the markets that work

**Verdict: the rejection stands, now for a better reason. The edge was real
and tradeable in 2011–2016, decayed to nothing by 2017, and has returned only
to a level below what it costs to trade. It is not a cost problem that cheaper
execution can fix.**

Measured 2026-10-09 with `scripts/hourly_reversal_focused.py`.

---

## Why it was worth re-testing

Hourly cross-sectional reversal across 16 CME markets was rejected earlier:
out-of-sample Sharpe 0.32, t=0.76. That test pointed the signal at every
market in the file. The daily work since then established that only eight
markets carry a measurable reversal edge and the other eleven carry none
(Sharpe +0.13, OOS −0.03 — docs/UNIVERSE_WIDENING.md). So the rejection might
have measured eight good streams diluted by eight empty ones.

It didn't, but the dilution was real and worth knowing about.

## The caveat, stated before the result

Choosing these eight *because* they showed a daily edge is a selection made on
overlapping data. This is not a clean out-of-sample test of "does hourly
reversal work". Two things limit the damage without eliminating it: the
selection was made at a different horizon (daily) from the test (hourly), and
the configuration is chosen in-sample and reported out-of-sample against a
final holdout no earlier test has touched — calendar **2026**, which lies
beyond the end of the Databento panel.

## Result

Configuration chosen in-sample on 2011–2019 (`look=1, hold=8, k=3`), then
frozen. Cost 0.75bp round trip, the measured micro-futures figure.

| | gross/yr | breakeven | net @0.75bp | Sharpe |
|---|---|---|---|---|
| eight markets, in-sample | +6.60% | 0.89bp | +1.01% | +0.21 (t=0.64) |
| all 20 markets, in-sample | +4.99% | 0.56bp | −1.59% | −0.09 |
| **eight markets, out-of-sample** | **−1.99%** | **−0.33bp** | −6.40% | −0.73 |
| all 20 markets, out-of-sample | −8.21% | −1.22bp | −12.93% | −0.98 |
| **eight markets, 2026 holdout** | +3.66% | 0.41bp | −2.90% | −0.08 (t=−0.07) |

Focusing on the eight **does** help — out-of-sample gross improves from −8.21%
to −1.99%, and in-sample breakeven from 0.56bp to 0.89bp. The dilution
hypothesis was directionally right. It is nowhere near enough: even in-sample
the edge clears its cost by 0.14bp, and out-of-sample the **gross** edge is
negative, which no cost reduction can repair.

## The reason, which is the useful part

Gross edge before any costs, by three-year block:

| period | gross/yr | breakeven | tradeable at 0.75bp? |
|---|---|---|---|
| 2011–2013 | **+17.94%** | 2.07bp | yes, comfortably |
| 2014–2016 | **+11.48%** | 1.39bp | yes |
| 2017–2019 | −1.03% | −0.18bp | no |
| 2020–2022 | −1.12% | −0.19bp | no |
| 2023–2025 | +4.25% | 0.67bp | no, just below |
| 2026 (holdout) | +3.66% | 0.41bp | no |

That is a textbook decay profile: a real edge, competed away as participants
arrived, partially returning but never back above its own transaction cost.
It matches what this repo observed earlier about intraday reversal paying in
2011 and not now, and it explains the original rejection properly — the signal
is not weak, it is *gone*, and was already gone for most of the period that
test covered.

### Does the cheapest possible execution rescue it?

0.34bp round trip is the best measured micro figure (MNQ). Even there:

| period | net/yr @0.34bp | Sharpe |
|---|---|---|
| 2023–2025 | +2.08% | +0.39 (t=0.65) |
| 2026 holdout | +0.63% | +0.16 (t=0.14) |

Neither is statistically distinguishable from zero, and both are worse than
the daily book on the same markets. Execution is not the binding constraint.

## The contrast that matters

The same eight markets, same reversal idea, two horizons:

| horizon | 2010s | 2020s | direction |
|---|---|---|---|
| **hourly** | decayed to negative | below cost | **competed away** |
| **daily** | +0.59 | **+0.88** | **improving** |

Automation competed away the intraday reversal. It has not competed away the
daily one — the daily book's best decade is the current one. That is a
coherent story rather than a coincidence, and it is an argument for staying at
the daily horizon rather than a disappointment.

## Where this leaves the search

Three routes were open after docs/PROP_FIRMS.md. Two are now closed by
measurement:

- ~~more markets for the same edge~~ — tested, no (docs/UNIVERSE_WIDENING.md)
- ~~the same edge at a faster horizon~~ — tested, no (this document)
- **a second, uncorrelated edge** — untested, and the only one left

The 0.84 result worked because its two legs correlated +0.007; the gain came
from independence, not from breadth or speed. That is the shape to look for,
and it is now the only remaining route to the Sharpe ~1.2 a prop gate needs.
