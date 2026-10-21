# The FX-only book at FundedNext: the first configuration with positive EV
# that does not hinge on an unverifiable number

Measured 2026-10-21. Follows docs/FEES_AND_VENUE.md, which found that at a
CFD prop firm the deciding unknown is the overnight swap -- charged on every
position every night, and this book holds everything overnight.

## The idea

FundedNext offers swap-free accounts on every challenge, to anyone, with no
paperwork, for 10% more ($605 instead of $549.99 for $100k). It confirms
swap-free for "all major Forex pairs" (indices and commodities are not
mentioned). So a version of the book that trades ONLY the seven FX majors pays
no swap at all -- and FX was already where the overnight edge was strongest.

## The edge on FX majors alone (`scripts/fx_only_reversal.py`)

Seven majors expressed as the dollar value of each currency (CAD, CHF, JPY
inverted, or the ranking becomes a bet on the dollar), 2003-2026:

| | |
|---|---|
| gross Sharpe | **+0.49**, t = 2.35 |
| in-sample / out-of-sample | +0.40 / **+0.64** |
| every four-year block since 2004 | **positive** (+0.18 to +1.32) |
| turnover | 1.16x per day |
| breakeven cost | **0.58bp per side** |
| net @ 0.3 / 0.5 / 0.8 bp per side | +0.24 / +0.07 / −0.19 |

The most consistent edge measured in this project -- and thin.

## FundedNext rules (fundednext.com/cfds/stellar-2-step, help centre)

+8% then +5%, no time limit, 5 days minimum per phase; 10% maximum loss,
static from initial balance; 5% daily loss, real time with floating losses;
funded accounts cap aggregate open risk (stop-loss placement plus floating
losses) at 3% -- first breach forfeits that cycle's profit, a second cuts the
cap to 1% permanently; payouts at day 21 then every 14; 80% share; EAs
allowed (listed as "available with add-ons"); news and weekend holding
allowed.

## Two data problems, found and fixed

1. **Yahoo's FX highs and lows contain bad ticks** -- a 42% range on EUR/USD,
   60% on GBP/USD, 72 days of huge ranges with almost unchanged closes. They
   liquidated simulated accounts that real ones would not. Capped at each
   pair's 99th-percentile range or 1.5x the day's close move, whichever is
   larger (so the genuine 2015 franc de-peg survives).
2. **The daily-bar intraday check was far too pessimistic.** Measured on 665
   days of real hourly FX paths, the portfolio's true worst intraday dip is 29%
   of the every-leg-at-its-worst bound on average, 46% in the worst 5% of
   days. The tail ratio is used.

## Result (`scripts/fx_venue_compare.py`)

| venue | cost/side | swap | vol | pass | EV per attempt |
|---|---|---|---|---|---|
| FundedNext swap-free | 0.3bp | — | 8% | 35.9% | **+$1,391** |
| FundedNext swap-free | 0.3bp | — | 10% | 37.5% | **+$1,646** |
| FundedNext swap-free | 0.5bp | — | 8% | 27.9% | **+$675** |
| FundedNext swap-free | 0.5bp | — | 10% | 30.9% | **+$874** |
| FTMO 2-Step Swing | 0.3bp | 0% | 10% | 32.7% | +$1,668 |
| FTMO 2-Step Swing | 0.3bp | 1%/yr | 10% | 21.3% | +$467 |
| FTMO 2-Step Swing | 0.3bp | 2%/yr | 10% | 11.8% | −$175 |

Equal at zero swap; FTMO falls away the moment its (unpublished) FX swap is
1-2% a year. FundedNext does not depend on it.

A zero-edge control at FundedNext is roughly break-even, so the strategy is
contributing on the order of $400-1,000 per attempt above what the contract
alone is worth. The edge is doing real work here, not only the contract.

## Honest expectations

- Roughly **one attempt in three passes**, after about a year. Two in three
  cost $605 and nothing else.
- A funded account pays on the order of **$4,500-6,000 over two years**.
- Spread across attempts, that is about **$40-80 a month per account slot**,
  long run. Several slots scale it, but copies of one strategy pass and fail
  together. **This is not $600 a month.**

## Still unverified -- all readable from FundedNext's free trial

| | why it matters |
|---|---|
| spread + commission on the 7 majors | 0.3bp vs 0.5bp per side roughly halves EV |
| swap-free covers all 7 (incl. NZD, CAD, CHF, JPY pairs) | any swap reintroduces the FTMO problem |
| EA "add-on" cost | a recurring fee comes straight off EV |
| copying the same EA across your own accounts | decides whether slots can scale |
