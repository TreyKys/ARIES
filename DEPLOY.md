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

## 0. The one gate you must clear first: a reachable exchange

Binance's trading/data API is **geo-blocked from many cloud IPs** (returns
`HTTP 451`). Even *paper* mode needs the live price feed, so before anything
runs on the VPS you must make the exchange reachable, via one of:

- an Oracle Cloud region that isn't blocked, or
- a VPN / proxy on the VPS, or
- an exchange whose API your VPS can actually reach.

Verify from the VPS before deploying:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://fapi.binance.com/fapi/v1/time
# 200 = reachable, 451 = blocked
```
The historical data vault (`data.binance.vision`) is NOT blocked, which is
how backtests ran — but live trading needs the API itself.

## 1. Paper run (no real money — do this for the 2 months first)

```bash
git clone https://github.com/TreyKys/ARIES.git && cd ARIES
cp .env.example .env        # fill SUPABASE_URL/KEY for the dashboard (optional)
docker compose up -d --build
docker compose logs -f aries
```
This runs the paper portfolio on live prices with simulated fills, reporting
to your dashboard. Watch for ~2 weeks and confirm it tracks the backtest
before risking anything.

## 2. Validate without Docker (optional)

```bash
pip install -r requirements.txt
# replay on history (works anywhere, no exchange needed):
python run_aries.py --replay --pairs ETHUSDT,SOLUSDT,LINKUSDT --tf 15m --capital 100
```

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
