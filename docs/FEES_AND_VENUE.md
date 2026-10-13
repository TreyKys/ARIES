# Fees, and why the venue matters more than the strategy

Measured 2026-10-13. The question: the grid failed on fees; how do we interact
with the market without paying so much? Prop firm required, no own capital.

**Short answer: the fee problem cannot be engineered away for this edge at
Phidias, but it largely disappears at a different kind of prop firm. Moving
the same strategy from Phidias (futures) to an FTMO-style 2-Step Swing
account (CFDs) changes expected value per attempt from about −$75 to roughly
+$900 to +$3,000 — CONDITIONAL on one number not yet verified: FTMO's
overnight swap markup. That number can be read for free from FTMO's trial
account before anything is spent.**

---

## 1. Phidias, verified from the firm's own rules page

| fact | consequence |
|---|---|
| "fully automated trading … is not permitted"; semi-automated only, trader places and manages every order | the bot cannot trade a Phidias account — it must print a ticket (built: `--ticket`) |
| floor set at end of day, but liquidation "if your balance reaches … your drawdown limit" during the day | intraday breach; the first prop simulation (EOD-only) overstated pass rates |
| up to 5 funded Premium accounts; copy trading allowed within that | scale is capped at 5 identical accounts |
| commission per side per contract: MES/MNQ $0.75, MGC $1.10, SIL $1.50, MCL $0.90, M6E/M6A $0.64 (Tradovate) | cost is FIXED PER CONTRACT, so small contracts are dear per dollar |
| calendar spreads and illiquid contracts forbidden; news trading allowed | no impact on this book |

## 2. Where the fees actually go

Real round-trip cost per contract, at current prices: **MNQ 0.36bp, MES 0.70,
MYM 0.78, MGC 0.70, SIL 1.15, M2K 1.43, M6E 1.81, MCL 3.15, M6A 3.27.** A nine-
fold spread. The flat 1.5bp the backtest used was too dear for six contracts
and too cheap for three — and this book holds most of its contracts in the
cheap-notional FX micros, where the fixed commission bites hardest.

At Phidias's real schedule, **fees consume ~60% of gross** (`scripts/
fee_decomposition.py`). The cause is not the rate, it is turnover: **the book
trades 1.32x its entire gross exposure every day.**

### The structural trap

A Phidias "$100k" account is really $3,000 of drawdown. That forces the
smallest contracts. The smallest contracts have the highest commission per
dollar. Full-size contracts cost half as much per dollar — and one of them
would exceed the entire $3,000 buffer. **The drawdown rule forces you onto the
most expensive instruments.**

## 3. Every way to cut the fee bill, tested

| attack | result |
|---|---|
| run it flat at the close, unlocking every cheaper prop firm | **dead.** 78% of the edge is earned overnight (Sharpe 0.60); the day session carries 21% (0.28, t=0.85) |
| hold longer / overlapping portfolios | **dead.** The signal pays on day 1 only (t=2.02); day 2 reverses (−0.38). Every N>1 lowers net Sharpe |
| partial adjustment toward target (Gârleanu–Pedersen) | **dead**, same reason: monotonically worse as turnover falls |
| trade at settlement (TAS) | not confirmed for MES/MNQ; confirmed only for micro gold/silver/copper — the markets that lose money in this book |
| perfect limit-order fills (zero spread) | ceiling only: net Sharpe 0.25 → 0.42. **The per-contract commission alone costs 0.25 of Sharpe** |
| trade only on high-dispersion days | rejected: in-sample +0.04, out-of-sample +2.05. That is a regime amplifier, not a filter |
| carry, a slow edge with no turnover | fee-proof as designed (4×/yr vs 362×), uncorrelated (−0.03), but weak (net ~0.2, t≈1) and decayed: IS +0.59, OOS −0.10, 2023–25 −0.73 |

## 4. Data-integrity checks that changed the numbers

- **Databento daily bars include a Sunday-evening stub** (16.4% of rows; 311
  "sessions" a year). Left in, the reversal book measured 0.00 gross. Fixed in
  `ares/carry_signal.py`.
- **Close time does not create the edge.** On synchronised hourly prices the
  book scores 0.37–0.80 for any "close" from 11:00 to 00:00 New York
  (`scripts/reversal_close_time.py`; an earlier version of that script
  sampled wrongly and is fixed).
- **Roll jumps do not inflate it** (adjusted 0.56 vs raw 0.54).
- **Reconciled gross Sharpe ≈ 0.5** on clean, synchronous futures data. Net of
  Phidias's real costs, between **−0.01 and +0.25** depending on construction.
- **The edge is strongly regime-dependent.** Under real costs the replay lost
  money every year 2001–2006 (from $100k to $9k), then recovered to $176k by
  2026. On own capital that is ruinous. On a prop account it costs one fee.

## 5. Phidias, with its real rules

`scripts/phidias_true_ev.py`: hourly intraday paths, real per-contract costs,
$180 fee (the firm's own code; activation waived on one-time payment).

| vol | pass (intraday breach) | EV per attempt |
|---|---|---|
| 5% | 12.4% | −$82 |
| 12% | 14.2% | −$49 |
| 18% | 17.4% | +$6 |

Even with trading made free, EV tops out around +$159. **This corrects
docs/PROP_FIRMS.md**, whose +$400–650 came from end-of-day breach checks and
the old flat cost model.

## 6. The venue, not the strategy

`scripts/ftmo_vs_phidias.py`. FTMO 2-Step, verified from ftmo.com: +10% then
+5%, 5% daily loss, 10% maximum loss, Swing account allows overnight and
weekend holding, fee refunded with the first payout. Expert advisors permitted
on MT4/MT5 (copy-trading and HFT are not).

Three structural differences, each pointing the same way:

1. **Gate shape.** 1:1 then 1:2 with a STATIC floor, against Phidias's 2:1
   with a TRAILING floor.
2. **Buffer.** $10,000 of drawdown on a $100k account, against $3,000. Income
   on a prop account scales with the buffer, not the headline size.
3. **Cost structure.** CFDs trade in fractional lots with cost proportional to
   notional, so small size carries no per-contract penalty. FX legs —
   the book's most expensive at Phidias — are roughly 2–5× cheaper. The new
   cost is an overnight SWAP on every position, every night.

| swap markup | net Sharpe of book | best EV per attempt |
|---|---|---|
| 0.0%/yr | +0.25 | **+$2,983** (pass 38%) |
| 1.5%/yr | +0.02 | **+$1,198** (pass 28%) |
| 3.0%/yr | −0.21 | +$485 (pass 19%) |

### Why EV can be positive at near-zero Sharpe

A funded account is a **free call option on your trading P&L**: you keep 80%
of the gains and the firm absorbs the losses down to the floor. Option value
rises with room to move. FTMO's wide static floor gives room; Phidias's tight
trailing floor removes it. At 1.5% swap the book's Sharpe is +0.02, yet EV is
still about +$1,200 — the structure is doing the work.

This is also the honest caveat. A result that holds at near-zero Sharpe is
mostly about the CONTRACT, not the strategy, and it depends on modelling the
firm's rules correctly. Real accounts can be reviewed and closed; payouts
depend on the firm continuing to honour them; spreads below are estimates.

## 7. What is verified and what is not

| | status |
|---|---|
| FTMO targets, loss limits, Swing overnight/weekend, refund, EA permission | verified, firm's site |
| FTMO FX commission $2.50/lot/side; indices commission-free | verified, FTMO update Sep 2025 |
| CFD spreads per instrument | **estimated** |
| gold/silver fee | **unknown** |
| **overnight swap markup** | **unknown — and it decides the answer** |
| fee ~$590 | estimated (≈€540) |

**How to resolve it at no cost:** open FTMO's free trial account, open MT5's
symbol specification for US100, US500, US30, XAUUSD, XAGUSD, USOIL, EURUSD
and AUDUSD, and read the long and short swap and the typical spread. Below
1.5%/yr net markup, the venue switch is clearly positive expected value;
above 3%, it is not.

## 8. Changes to the runner

- `--ticket --equity N` prints today's orders for **manual** entry and sends
  nothing (Phidias-compliant). `--ticket-filled` records them as positions.
  The ticket is mirrored to the monitor, so it shows on the hosted dashboard.
- Default strategy is now reversal-only. Under real costs it is level with the
  combined book (0.35 vs 0.34), so this is the simpler book at no measured cost.
- `--replay` now charges Phidias's per-contract schedule instead of a flat
  rate. Its numbers are lower as a result, and accurate.
