"""OKX market data: the reachable exchange for this deployment.

Binance's trading API returns HTTP 451 from cloud IPs, which blocked the whole
paper-trading phase (see DEPLOY.md). OKX's public endpoints answer normally from
the same host and serve everything the carry engine needs -- spot price, perp
price and the live funding rate -- with no API key for read-only data.

Funding-rate HISTORY still comes from data.binance.vision (also not blocked),
which is fine: that is backtest input, not live state.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

BASE = "https://www.okx.com/api/v5"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(path: str, timeout: float = 20.0) -> List[dict]:
    req = urllib.request.Request(f"{BASE}{path}", headers=UA)
    payload = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX error {payload.get('code')}: {payload.get('msg')}")
    return payload.get("data", [])


def to_okx_spot(pair: str) -> str:
    """ETHUSDT -> ETH-USDT"""
    if pair.endswith("USDT"):
        return f"{pair[:-4]}-USDT"
    raise ValueError(f"unsupported pair {pair}")


def to_okx_swap(pair: str) -> str:
    """ETHUSDT -> ETH-USDT-SWAP"""
    return f"{to_okx_spot(pair)}-SWAP"


@dataclass
class CarryQuote:
    pair: str
    spot: float
    perp: float
    funding_rate: float        # per interval, as a decimal
    next_funding_ms: int
    basis_bps: float           # (perp/spot - 1) in bps; the hedge's tracking error


def fetch_carry_quote(pair: str) -> CarryQuote:
    spot = float(_get(f"/market/ticker?instId={to_okx_spot(pair)}")[0]["last"])
    swap_id = to_okx_swap(pair)
    perp = float(_get(f"/market/ticker?instId={swap_id}")[0]["last"])
    f = _get(f"/public/funding-rate?instId={swap_id}")[0]
    basis = (perp / spot - 1.0) * 1e4 if spot > 0 else 0.0
    return CarryQuote(pair=pair, spot=spot, perp=perp,
                      funding_rate=float(f["fundingRate"]),
                      next_funding_ms=int(f["fundingTime"]),
                      basis_bps=basis)


def fetch_funding_now(pair: str) -> float:
    return float(_get(f"/public/funding-rate?instId={to_okx_swap(pair)}")[0]["fundingRate"])


def reachable() -> bool:
    """Cheap preflight so a deploy fails loudly, not silently."""
    try:
        _get("/public/time", timeout=10.0)
        return True
    except Exception:  # noqa: BLE001
        return False
