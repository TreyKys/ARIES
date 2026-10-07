# Deploying ARES for the 2-month run

## !! CORRECTION: the hedged grid does not work. Do not deploy it. !!

An earlier version of this file claimed the hedged-grid portfolio made
~22%/yr at ~2% max drawdown. That was a **modelling bug**, now fixed. The
backtest booked the long grid leg's round-trip profits while charging the
short hedge only fees -- it never marked the hedge's own P&L.

The identity it violated: for any book, price P&L = sum(position x dPrice).
A book held delta-neutral earns **nothing** from price movement, only carry.
The short hedge is a mirror-image grid that shorts as price falls and covers
as it rises, giving back exactly what the long grid earns.

Honestly marked, the same 18-month ETH/SOL/LINK run is:

    $100 -> $68.34  (-22.4%/yr), max drawdown 36.45%, 3614 hits

Fees alone (3614 hits x 14bps x $5 unit ~ $25) plus hedge-rebalance drag
account for the loss. `ares/grid.py` and `ares/grid_engine.py` now mark both
legs, and `tests/test_grid.py` pins the identity shut.

**The only validated market-neutral edge in this repo is funding carry**
(long spot + short perp, collecting funding). That needs spot AND perps in
one account, so it is not prop-firm compatible. See docs/STRATEGY_RESEARCH.md.

## 0. The exchange gate is CLEARED: use OKX, not Binance

Binance's trading API is geo-blocked from cloud IPs (`HTTP 451`), which blocked
this whole phase. **OKX's public API answers normally from the same host** and
serves everything the carry engine needs — spot price, perp price and the live
funding rate — with no API key for read-only data. `ares/okx.py` wraps it.

Verify from the VPS:
```bash
curl -s "https://www.okx.com/api/v5/public/time"            # OKX: works
curl -s -o /dev/null -w "%{http_code}\n" \
     https://fapi.binance.com/fapi/v1/time                  # Binance: 451
```
Funding-rate HISTORY still comes from `data.binance.vision` (not blocked), which
is fine — that is backtest input, not live state.

## 1. What the paper run can and cannot tell you

**It cannot validate the edge.** The standard error of a Sharpe ratio depends on
elapsed YEARS, not on how many bars you collect; six weeks gives SE ~ +/-2.9,
which is no information at all. Do not conclude anything about profitability
from it, in either direction.

**It verifies the things that actually break live**, which is why it is worth
the six weeks:
- both legs fill, and the hedge stays matched in size
- basis tracking error is as small as the backtest assumes (currently ~3-7bp;
  the engine logs it every poll)
- funding is credited once per settlement window, not double-counted
- the engine survives restarts, network drops and OKX rate limits
- realised fees match the modelled 5bp/leg

## 2. Paper run (no real money — do this for the 6 weeks first)

```bash
git clone https://github.com/TreyKys/ARIES.git && cd ARIES
cp .env.example .env        # SUPABASE_URL/KEY for the dashboard (optional)
docker compose up -d --build
docker compose logs -f aries
```

## 3. Validate without Docker

```bash
pip install -r requirements.txt
python scripts/fetch_funding_history.py ETHUSDT BTCUSDT     # real funding, 6.7yr
python run_aries_carry.py --replay --pairs ETHUSDT,BTCUSDT --capital 50
# -> $50 -> $136.95 (+16.10%/yr) at 2x leverage over 6.7yr
```

## 4. What the numbers actually are

Validated on 6.7 years of real Binance funding history, unlevered, single pair:

| pair | return | max drawdown |
|---|---|---|
| ETHUSDT | +10.2%/yr | 1.07% |
| BTCUSDT | +9.0%/yr | 1.42% |
| SOLUSDT | +0.2%/yr | — (no carry; do not trade it) |

Always-on beats every gating scheme tested. A `rate > 0` gate returned
**+0.0%/yr with 36% drawdown** because fees consumed the entire carry. The
engine's hysteresis default (exit below -3bp, re-enter above +0.5bp) was
validated against the real series and is within noise of always-on.

**The carry is decaying.** Gross by year on ETH: 2021 +37.5%, 2022 +0.8%,
2023 +8.3%, 2024 +13.0%, 2025 +4.9%, 2026 +1.9%, with ~30% of 2026 intervals
negative. At the time of writing ETH funding is **-4.0%/yr** (you would pay)
and BTC **+1.2%/yr**. Plan for 2-5%/yr, not the long-run average. On $50 that
is a few dollars a year — real, market-neutral, and small. The dollars scale
with capital, not with the engine.

## 3. Going live (only after paper proves out)

Live needs the real two-leg broker wired in (`ares/execution.py::CcxtBroker`,
post-only grid + maker-then-taker hedge) plus funded TESTNET→real keys in
`.env`. Start at the smallest real stake, watch closely, scale only after
real fills track paper. Keep leverage modest (the hedge is the protection,
not a return multiplier).

## Risk controls already built in
- Hedge neutralises direction (grid can't accumulate a runaway bag).
- Cost-aware spacing floor (every rung clears fees).
- Optional smart hedge dial (`unhedged_ratio`) to ride confirmed uptrends —
  higher return, higher drawdown; off by default.
- Never run the grid leveraged and unhedged.
