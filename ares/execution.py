"""Order execution layer with per-leg fee/safety policy.

A grid rung and a hedge adjustment want different things:

- Grid rungs are resting limit orders -> POST_ONLY (guaranteed maker fee;
  if a fast move skips the rung, we simply didn't trade it -- harmless).
- The hedge must actually execute or we're left directionally exposed ->
  MAKER_THEN_TAKER: try a cheap post-only maker first, but if it doesn't
  fill within a short timeout, cross the spread and pay taker rather than
  sit unhedged.

CcxtBroker is the real implementation (run on a reachable host). SimBroker
models the same policy for paper/replay and for unit tests. Live exchange
calls can't be tested from a geo-blocked sandbox, so the fill *decision
logic* is what the tests cover.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderType(str, Enum):
    POST_ONLY = "post_only"            # maker or nothing
    MAKER_THEN_TAKER = "maker_then_taker"  # try maker, fall back to taker
    TAKER = "taker"                    # cross the spread now


@dataclass(frozen=True)
class OrderPolicy:
    grid: OrderType = OrderType.POST_ONLY
    hedge: OrderType = OrderType.MAKER_THEN_TAKER
    hedge_timeout_s: float = 8.0


@dataclass
class Fill:
    filled: bool
    price: float = 0.0
    qty: float = 0.0
    fee: float = 0.0
    is_maker: bool = False
    note: str = ""


class SimBroker:
    """Deterministic broker for paper/replay and tests.

    `maker_fillable` decides whether a post-only order would rest (True) or
    be rejected for crossing (False) -- the caller supplies it from the
    current spread/price in live-paper; tests pass it explicitly.
    """

    def __init__(self, maker_fee: float = 0.0002, taker_fee: float = 0.0005):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee

    def place(self, side: str, qty: float, ref_price: float, order_type: OrderType,
              *, maker_fillable: bool = True) -> Fill:
        if order_type is OrderType.TAKER:
            return Fill(True, ref_price, qty, ref_price * qty * self.taker_fee, False, "taker")
        if order_type is OrderType.POST_ONLY:
            if maker_fillable:
                return Fill(True, ref_price, qty, ref_price * qty * self.maker_fee, True, "maker")
            return Fill(False, note="post-only rejected (would cross)")
        # MAKER_THEN_TAKER
        if maker_fillable:
            return Fill(True, ref_price, qty, ref_price * qty * self.maker_fee, True, "maker")
        return Fill(True, ref_price, qty, ref_price * qty * self.taker_fee, False, "taker-fallback")


class CcxtBroker:
    """Live broker over ccxt. Run on a host that can reach the exchange."""

    def __init__(self, exchange, policy: Optional[OrderPolicy] = None):
        self.ex = exchange                 # a ccxt(.async_support) exchange instance
        self.policy = policy or OrderPolicy()

    async def place(self, symbol: str, side: str, qty: float, ref_price: float,
                    order_type: OrderType, reduce_only: bool = False) -> Fill:
        try:
            if order_type is OrderType.TAKER:
                o = await self.ex.create_order(symbol, "market", side, qty,
                                               params={"reduceOnly": reduce_only})
                return self._fill(o, maker=False)

            params = {"postOnly": True, "reduceOnly": reduce_only}
            o = await self.ex.create_order(symbol, "limit", side, qty, ref_price, params=params)

            if order_type is OrderType.POST_ONLY:
                return self._fill(o, maker=True)

            # MAKER_THEN_TAKER: wait briefly for the maker order to fill
            filled = await self._await_fill(symbol, o["id"], self.policy.hedge_timeout_s)
            if filled:
                return self._fill(filled, maker=True)
            await self._safe_cancel(symbol, o["id"])
            o = await self.ex.create_order(symbol, "market", side, qty,
                                           params={"reduceOnly": reduce_only})
            return self._fill(o, maker=False, note="taker-fallback")
        except Exception as e:  # noqa: BLE001 — surface, caller decides
            return Fill(False, note=f"order error: {e}")

    async def _await_fill(self, symbol, order_id, timeout_s):
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            o = await self.ex.fetch_order(order_id, symbol)
            if o.get("status") == "closed":
                return o
            await asyncio.sleep(1.0)
        return None

    async def _safe_cancel(self, symbol, order_id):
        try:
            await self.ex.cancel_order(order_id, symbol)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _fill(o: dict, *, maker: bool, note: str = "") -> Fill:
        price = o.get("average") or o.get("price") or 0.0
        qty = o.get("filled") or o.get("amount") or 0.0
        fee = (o.get("fee") or {}).get("cost", 0.0) if isinstance(o.get("fee"), dict) else 0.0
        return Fill(True, float(price or 0), float(qty or 0), float(fee or 0), maker, note or ("maker" if maker else "taker"))
