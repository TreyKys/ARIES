# Prop firms that allow overnight holds — and whether ours can use one

**Verdict: one firm qualifies on the rules. The strategy still fails its
economics, and the reason is the strategy, not the firm.**

Researched 2026-10-09. Prop firm terms change often; re-check before paying.

---

## 1. Why this search was needed

The combined book holds positions overnight. Almost every futures prop firm
force-liquidates before the daily close, which rules the strategy out
mechanically, whatever its returns. So the first question was simply: does
any firm permit overnight holds on a funded account?

## 2. Firms checked

| firm | overnight? | weekend? | source |
|---|---|---|---|
| **Phidias — Premium** | **yes** | **yes** | firm's own rules page |
| Phidias — Fundamental / Express | no | no | firm's own rules page |
| Apex Trader Funding | no — flat by 4:59pm ET | no | firm's published rules |
| Topstep | no — flat by 3:10pm CT | no | firm's rules |
| MyFundedFutures | no — auto-close 4:10pm ET | no | help centre, all plans |
| Tradeify | no — auto-liquidation | no | firm's rules |
| Take Profit Trader | no — auto-close 4:55pm ET | no | firm's rules |
| Lucid Trading | no — flat by 4:45pm ET | no | firm's rules |
| Bulenox | no — flat by 3:59pm CT | no | firm's rules |
| FundedNext Futures | no | no | help centre |
| Funded Futures Family | **no** — flat by 4:15pm ET | no | firm's FAQ |
| BluSky | no — auto-liquidates pre-close | no | reviews, consistent |
| Goat Funded Futures | disputed; help centre says no | disputed | conflicting |
| Alpha Futures | no on simulated; yes on *live* only | — | help centre |

Affiliate review sites contradict each other constantly on this, and several
name firms as swing-friendly that their own help centres say otherwise. Only
rows sourced to a firm's own pages should be trusted.

**Alpha Futures is worth one footnote:** overnight holding is permitted on
their *live* stage, not the simulated funded stage. That is a different
product — real capital, reached only after a long simulated track record.

## 3. Phidias Premium, the one that qualifies

From the firm's own rules page:

| | 50K | 100K | 150K |
|---|---|---|---|
| EOD trailing drawdown | $2,500 | $3,000 | $4,500 |
| Floor stops trailing (funded) | $50,100 | $100,100 | not stated |
| Daily loss limit | none | none | none |
| Max contracts | 10 mini / 100 micro | 14 / 140 | 17 / 170 |
| Evaluation profit target | $4,000 | $6,000 | $9,000 |
| Minimum evaluation days | 1 | 1 | 1 |
| Payout cap per cycle | $2,000 | $2,500 | $2,750 |
| A day counts toward payout only if it made | $150 | $200 | $250 |

Profit split is progressive: 75% / 80% / 85% / 90%, then 100% from the fifth
payout. Payouts every 5 qualifying trading days.

Three of these are genuinely good for us:

- **Overnight and weekend holds allowed.** The blocker is gone.
- **The floor locks** at the account size plus $100 once funded. This is the
  "drawdown floor that locks at breakeven" that was asked for several months
  ago; it means that once you are $3,100 up, you can never lose more than
  your own profits.
- **140 micro contracts** is far more than the 8 this book needs.

## 4. So it comes down to arithmetic

`scripts/prop_firm_study.py` takes the strategy's **real** daily returns from
the 26-year replay, scales them to a chosen volatility, and bootstraps them
forward through Phidias's actual rules — the trailing floor, the locking
level, the payout cycle, the minimum-profit day rule, the cap, the split and
both fees. Block bootstrap, not day-by-day: a drawdown limit is a bet on how
losses cluster, and resampling single days would quietly make every rule look
easier to survive.

Phidias Premium 100K, 1,500 paths per row, $1,000 withdrawal buffer:

| vol target | return/yr | pass eval | breach within 1yr | $/month if funded | EV per attempt |
|---|---|---|---|---|---|
| 3% | 1.2% | 8.6% | 47% | $49 | **−$412** |
| 5% | 2.1% | 25.7% | 83% | $127 | **−$96** |
| 8% | 3.3% | 29.9% | 98% | $144 | **+$23** |
| 12% | 5.0% | 30.1% | 99% | $175 | **+$136** |
| 18% | 7.5% | 31.1% | 96% | $241 | **+$404** |
| 25% | 10.4% | 32.9% | 97% | $220 | **+$368** |

Best case: pay $450, pass about a third of the time, and expect roughly
**+$400 a year** net of fees. That is not an income. It is a coin flip with a
small positive edge and enormous variance.

Letting the evaluation run for five years instead of one does not rescue it
(pass rate 35%, but **100%** breach within a year of funding). Leaving a
bigger buffer when withdrawing does not either — tested at $0, $1k, $2k and
$3k, it moves nothing by more than a few percent.

## 5. Why — and this is the general result

The evaluation is a **2:1 bet**: make $6,000 before losing $3,000. For a
strategy whose edge is small relative to its noise, the probability of
hitting the target before the floor is almost exactly

    P(pass) = drawdown / (target + drawdown) = 3,000 / 9,000 = 33%

which is what the simulation returns at every volatility above 5%. The
strategy's edge contributes almost nothing over the 20–70 days the evaluation
takes. **You are not being paid for the edge; you are buying a one-in-three
ticket for $450.**

The funded phase has the mirror problem. The floor locking at account + $100
means "you may never give back your profits". At Sharpe 0.41 over a year,
the chance of a drawdown that deep is ~96%.

## 6. The bar, so this is a number and not a shrug

Same rules, same simulation, synthetic returns swept by Sharpe (each row
shows its best volatility):

| Sharpe | vol | return/yr | pass eval | breach 1yr | $/month | EV per attempt |
|---|---|---|---|---|---|---|
| **0.4** (what we have) | 25% | 10% | 28% | 99% | $214 | $220 |
| 0.8 | 5% | 4% | 36% | 93% | $177 | $263 |
| 1.2 | 5% | 6% | 44% | 88% | $218 | **$643** |
| 1.6 | 5% | 8% | 56% | 85% | $315 | **$1,564** |
| 2.0 | 5% | 10% | 68% | 78% | $417 | **$2,839** |
| 3.0 | 25% | 75% | 44% | 83% | $1,330 | **$6,422** |

The economics turn genuinely positive at about **Sharpe 1.2**, and become
worth doing at 1.6–2.0. The combined book measures **0.41 ± 0.21** on the
eight micro futures available to it (0.84 over 57 years on the full daily
universe, which is the honest upper bound if more markets were added).

Note what the table also says: raising volatility does not help a weak
strategy. Every row at Sharpe 0.4 lands in the same place, because the gate
is a ratio and leverage cancels out of a ratio. Only quality moves it.

## 7. Where that leaves the three options

- **Prop firm now:** Phidias Premium is the only one that will let the
  strategy run at all, and the expected value is roughly break-even. It is
  not a bad firm — it is the wrong strategy for the gate.
- **Raise the strategy to Sharpe ~1.2+:** the only route that makes the prop
  model pay. That means more markets (the 57-year book measured 0.84 with a
  wider universe than the 8 micros available here) or a second uncorrelated
  edge, not more leverage.
- **Own capital at a broker:** no gate, no fee, no split, no drawdown rule
  that ends the account. ~4%/yr at natural size. Slow, but the edge is kept
  rather than gambled against a 2:1 gate.

---

## Sources

Firms' own pages: [Phidias rules](https://phidiaspropfirm.com/rules),
[Phidias swing](https://phidiaspropfirm.com/swing-allowed),
[Funded Futures Family FAQ](https://www.fundedfuturesfamily.com/faq/can-i-hold-positions-overnight/),
[Alpha Futures live-account rules](https://help.alpha-futures.com/en/articles/11023753-live-account-rules-and-parameters),
[Goat Funded Futures instant-funded specs](https://help.goatfundedfutures.com/en/articles/14095625-what-are-the-instant-funded-specifications).

Comparisons used for leads, then checked against the above:
[Phidias firm comparison](https://phidiaspropfirm.com/education/best-futures-prop-firms),
[PropfirmXL](https://propfirmxl.com/futures-prop-firms-that-allow-overnight-holding/),
[Vetted Prop Firms](https://vettedpropfirms.com/futures-prop-firms-that-allow-overnight-holding/),
[QuantVPS swing list](https://www.quantvps.com/blog/prop-trading-firms-that-support-swing-trading),
[Propvator on MFFU](https://propvator.com/blog/my-funded-futures-overnight-holding/).
