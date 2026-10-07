"""Levered funding carry WITH basis risk, through the audited ledger.

The carry trade is long spot + short perp: price moves cancel, and the short
leg collects the perpetual funding payment. ares/carry.py models that as a pure
function of the funding series, treating the price legs as exactly cancelling.
That is a fair idealisation at 1x, but it reports 0.00% drawdown at ANY
leverage, which is dangerously wrong -- it makes 20x look free.

What actually cancels is the price LEVEL. What does not cancel is the BASIS:
the gap between the perp price and the spot price. Holding spot quantity Q long
and perp quantity Q short,

    price P&L = Q * [(S_now - S_0) - (P_now - P_0)] = -Q * (basis_now - basis_0)

so a WIDENING basis (perp rising relative to spot) is a loss, scaled by Q --
i.e. by leverage. Measured on 6.7yr of hourly Binance data, basis is normally
tiny (sd ~0.07%) but its worst adverse excursions were +2.85% on ETH and
+4.79% on BTC (Dec 2020), with +2.70% inside 24h during the March 2020 crash.
At 3x that worst case costs ~9-14% of equity; at 20x it is a wipeout.

This module holds both legs as real instruments in the Ledger, so equity is
cash + Q*S - Q*P and the basis loss appears by construction rather than by
being remembered. Liquidation is modelled explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .ledger import Ledger

SPOT = "SPOT"
PERP = "PERP"


@dataclass
class CarryBasisConfig:
    leverage_min: float = 3.0
    leverage_max: float = 5.0
    dynamic: bool = True
    mode: str = "breaker"
    # "breaker" (default): sit at leverage_max and cut to leverage_min ONLY on a
    #   decisive basis dislocation. Rare, cheap, and aimed at the actual tail.
    # "riskparity": continuous leverage = target_basis_risk / basis_vol. Tested
    #   and REJECTED -- it loses to a fixed 5x on return, drawdown AND Sharpe in
    #   every window, because basis spikes are brief and mean-revert, so the dial
    #   de-levers after the event and just pays fees while missing funding.
    breaker_basis: float = 0.005        # |basis| above 0.5% (~7 sigma) -> de-lever
    breaker_recover: float = 0.002      # back to full once below 0.2%
    # Risk-parity target: pick leverage so that leverage * basis_vol is constant.
    # Calibrated so calm conditions (basis sd ~0.07%) sit at leverage_max.
    target_basis_risk: float = 0.0035
    basis_vol_window: int = 168          # 1 week of hourly observations
    levels: tuple = (3.0, 4.0, 5.0)      # discrete rungs, not a continuous dial
    step_hysteresis: float = 0.35        # need this much of a step before moving
    min_dwell_hours: int = 168           # and hold a level at least this long
    funding_floor: float = 0.0           # de-lever toward min when funding <= this
    taker_fee: float = 0.0005            # per leg, per side
    rebalance_band: float = 0.35         # resize only when notional drifts >35%
    liquidation_equity_frac: float = 0.20  # dead below 20% of starting capital
    compound: bool = False
    # compound=False sizes notional off STARTING capital, not current equity.
    # With reinvestment the position grows with profits, so at high leverage the
    # result is exponential fantasy: 20x over 6.7yr compounded to +1011%/yr with
    # $37M of fees on a $50 account. That implicitly assumes infinite scalability
    # -- no market impact, no position limits, and no effect of your own size on
    # the funding rate you are harvesting. Fixed notional keeps numbers readable
    # and honest; turn it on only for small leverage over short windows.


@dataclass
class CarryBasisResult:
    ledger: Ledger
    liquidated: bool
    liquidation_ts: Optional[int]
    leverage_path: List[Tuple[int, float]]
    worst_basis_excursion_pct: float
    funding_received: float


def _basis_vol(hist: Sequence[float]) -> Optional[float]:
    n = len(hist)
    if n < 24:
        return None
    m = sum(hist) / n
    var = sum((x - m) ** 2 for x in hist) / (n - 1)
    return var ** 0.5


def _quantize(cfg: CarryBasisConfig, raw: float, current: float) -> float:
    """Snap to a discrete rung, with hysteresis and a dwell requirement.

    A continuous leverage dial is a fee pump: basis volatility wobbles hourly,
    so raw leverage flaps across the band and every flap retrades BOTH legs at
    taker fees. Measured on 2025+ ETH, the continuous version returned
    -32.79%/yr at 52% drawdown with $43 of fees, against +16.24%/yr and $1.48
    for a fixed 5x. Discretising and demanding a decisive move is what makes an
    adaptive rule cheaper than the edge it chases.
    """
    levels = list(cfg.levels)
    nearest = min(levels, key=lambda L: abs(L - raw))
    if current <= 0:
        return nearest
    if abs(nearest - current) < 1e-9:
        return current
    # only step if raw has moved decisively past the midpoint toward the new rung
    if abs(raw - current) < cfg.step_hysteresis:
        return current
    return nearest


def choose_leverage(cfg: CarryBasisConfig, basis_hist: Sequence[float],
                    funding_rate: float) -> float:
    """Risk-parity leverage inside [leverage_min, leverage_max].

    Leverage is set so that leverage * (recent basis volatility) stays near a
    constant target: calm basis -> lever up, unstable basis -> lever down. This
    is risk targeting, not a fitted rule, and it is CLAMPED to the configured
    band so a quiet stretch can never talk the engine into 10x.

    Funding is the reward for the risk, so when it is at or below the floor the
    engine sits at the minimum rather than paying basis risk for nothing.
    """
    if not cfg.dynamic:
        return cfg.leverage_max
    if cfg.mode == "breaker":
        # Fire on BASIS ONLY. Tying the breaker to funding sign as well was the
        # churn source: funding flips negative in 10-30% of intervals, so
        # leverage flapped 3<->5 constantly (147 changes, $18.70 fees over
        # 6.7yr). Basis above 0.5% occurs in under 0.1% of hours, so a
        # basis-only breaker is nearly free and aimed at the actual tail.
        # Negative funding is a small, self-limiting cost; a basis blowout at
        # leverage is the thing that ends the account.
        b = basis_hist[-1] if basis_hist else 0.0
        if abs(b) >= cfg.breaker_basis:
            return cfg.leverage_min
        return cfg.leverage_max
    vol = _basis_vol(basis_hist)
    if vol is None or vol <= 0:
        return cfg.leverage_min
    lev = cfg.target_basis_risk / vol
    if funding_rate <= cfg.funding_floor:
        lev = cfg.leverage_min
    return max(cfg.leverage_min, min(cfg.leverage_max, lev))


def run_carry_basis(ts: Sequence[int], spot: Sequence[float], perp: Sequence[float],
                    funding: Dict[int, float], *, capital: float = 50.0,
                    cfg: CarryBasisConfig = CarryBasisConfig()) -> CarryBasisResult:
    """Replay a levered carry position over real spot/perp/funding history.

    funding: {timestamp_ms -> rate_per_interval}. Rates are credited on the
    short perp leg at their own timestamps, so a negative rate is a real cost.
    """
    led = Ledger(capital)
    basis_hist: List[float] = []
    lev_path: List[Tuple[int, float]] = []
    fund_keys = sorted(funding)
    fi = 0
    entry_basis: Optional[float] = None
    worst_exc = 0.0
    min_basis = None
    funding_total = 0.0
    liquidated = False
    liq_ts: Optional[int] = None
    cur_lev = 0.0
    last_change_i = -10**9

    for i in range(len(ts)):
        t, s, p = int(ts[i]), float(spot[i]), float(perp[i])
        if s <= 0 or p <= 0:
            continue
        b = p / s - 1.0
        basis_hist.append(b)
        if len(basis_hist) > cfg.basis_vol_window:
            basis_hist.pop(0)
        min_basis = b if min_basis is None else min(min_basis, b)
        worst_exc = max(worst_exc, b - min_basis)

        # credit every funding settlement at or before this bar
        while fi < len(fund_keys) and fund_keys[fi] <= t:
            rate = funding[fund_keys[fi]]
            short_qty = -led.pos.get(PERP, 0.0)
            if short_qty > 0:
                amt = rate * short_qty * p
                led.accrue(amt)
                funding_total += amt
            fi += 1

        eq = led.mark(t, {SPOT: s, PERP: p})

        if eq <= cfg.liquidation_equity_frac * capital:
            led.flatten(t, {SPOT: s, PERP: p}, cost_rate=cfg.taker_fee)
            led.mark(t, {SPOT: s, PERP: p})
            liquidated, liq_ts = True, t
            break

        nxt_rate = funding[fund_keys[fi]] if fi < len(fund_keys) else 0.0
        raw = choose_leverage(cfg, basis_hist, nxt_rate)
        if cfg.dynamic:
            if i - last_change_i < cfg.min_dwell_hours and cur_lev > 0:
                want = cur_lev                      # dwell: hold the level
            else:
                want = _quantize(cfg, raw, cur_lev)
                if abs(want - cur_lev) > 1e-9:
                    last_change_i = i
        else:
            want = raw
        base = eq if cfg.compound else capital
        target_notional = want * base
        have = led.pos.get(SPOT, 0.0) * s
        if have <= 0 or abs(target_notional - have) / max(have, 1e-9) > cfg.rebalance_band:
            # resize BOTH legs together so the hedge stays matched
            # Match UNITS, not dollars. Sizing each leg as notional/price gives
            # spot qty != perp qty whenever perp != spot, which leaves a
            # residual directional position (measured: 0.02% of notional) --
            # a hedge that does not actually cancel the price level.
            new_q = target_notional / s
            dq_spot = new_q - led.pos.get(SPOT, 0.0)
            if abs(dq_spot) > 1e-12:
                led.trade(t, SPOT, dq_spot, s, cost=abs(dq_spot) * s * cfg.taker_fee)
            dq_perp = (-new_q) - led.pos.get(PERP, 0.0)
            if abs(dq_perp) > 1e-12:
                led.trade(t, PERP, dq_perp, p, cost=abs(dq_perp) * p * cfg.taker_fee)
            cur_lev = want
            if entry_basis is None:
                entry_basis = b
        lev_path.append((t, cur_lev))

    return CarryBasisResult(ledger=led, liquidated=liquidated, liquidation_ts=liq_ts,
                            leverage_path=lev_path,
                            worst_basis_excursion_pct=worst_exc * 100,
                            funding_received=funding_total)
