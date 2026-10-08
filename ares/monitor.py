"""Monitoring state for the dashboard: equity, positions, trades, activity.

Writes a single JSON snapshot the dashboard polls. Deliberately append-only for
trades and activity, so the record of what the bot actually did survives a
restart and can be compared against the backtest later -- live-vs-expected is
the feedback loop that matters, far more than any adaptive logic (every
adaptive variant tested in this project made results worse; see
docs/STRATEGY_RESEARCH.md).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_TRADES = 500
MAX_ACTIVITY = 300
MAX_CURVE = 2000


@dataclass
class TradeRow:
    ts: int
    symbol: str
    side: str            # BUY / SELL
    qty: float
    price: float
    cost: float
    note: str = ""


@dataclass
class ActivityRow:
    ts: int
    level: str           # INFO / WARN / ERROR / TRADE
    source: str
    message: str


class Monitor:
    """Collects state and writes it atomically for the dashboard to read."""

    def __init__(self, path: str = "state/dashboard.json",
                 strategy: str = "combined", capital: float = 0.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.strategy = strategy
        self.capital = capital
        self.started = int(time.time() * 1000)
        self.trades: List[TradeRow] = []
        self.activity: List[ActivityRow] = []
        self.curve: List[List[float]] = []     # [ts_ms, equity]
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.equity = capital
        self.day_start_equity = capital
        self.connected = False
        self.last_error: Optional[str] = None
        self.mode = "paper"

    # --- recording ---------------------------------------------------------

    @staticmethod
    def _stamp(ts: Optional[int]) -> int:
        """Epoch ms for a row. A replay passes the BAR time; without it a
        57-year history would be stamped as having all happened today, making
        the trade table and the equity x-axis meaningless."""
        return int(time.time() * 1000) if ts is None else int(ts)

    def log(self, level: str, source: str, message: str,
            ts: Optional[int] = None) -> None:
        self.activity.append(ActivityRow(self._stamp(ts), level,
                                         source, message))
        del self.activity[:-MAX_ACTIVITY]

    def record_trade(self, symbol: str, qty: float, price: float,
                     cost: float = 0.0, note: str = "",
                     ts: Optional[int] = None) -> None:
        ts = self._stamp(ts)
        self.trades.append(TradeRow(ts, symbol,
                                    "BUY" if qty > 0 else "SELL",
                                    abs(qty), price, cost, note))
        del self.trades[:-MAX_TRADES]
        self.log("TRADE", symbol,
                 f"{'BUY' if qty > 0 else 'SELL'} {abs(qty):g} @ {price:,.4f}"
                 + (f"  ({note})" if note else ""), ts=ts)

    def set_positions(self, positions: Dict[str, Dict[str, Any]]) -> None:
        self.positions = positions

    def mark(self, equity: float, ts: Optional[int] = None) -> None:
        self.equity = equity
        self.curve.append([self._stamp(ts), round(equity, 2)])
        del self.curve[:-MAX_CURVE]

    def roll_day(self, ts: Optional[int] = None) -> None:
        """Reset the intraday P&L baseline. Call at each session open."""
        self.day_start_equity = self.equity
        self.log("INFO", "SYSTEM",
                 f"new session, day baseline ${self.equity:,.2f}", ts=ts)

    # --- derived -----------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        peak = max((e for _, e in self.curve), default=self.equity) or self.equity
        dd = (peak - self.equity) / peak * 100 if peak > 0 else 0.0
        return {
            "generated": int(time.time() * 1000),
            "started": self.started,
            "strategy": self.strategy,
            "mode": self.mode,
            "connected": self.connected,
            "last_error": self.last_error,
            "capital": self.capital,
            "equity": round(self.equity, 2),
            "pnl_abs": round(self.equity - self.capital, 2),
            "pnl_pct": round((self.equity / self.capital - 1) * 100, 3)
                       if self.capital else 0.0,
            "day_pnl_abs": round(self.equity - self.day_start_equity, 2),
            "drawdown_pct": round(dd, 2),
            "n_positions": sum(1 for p in self.positions.values()
                               if p.get("qty")),
            "n_trades": len(self.trades),
            # A futures position's notional is contracts * price * multiplier.
            # Replay positions are already in units (multiplier applied), so
            # they carry no "mult" and default to 1; live positions come back
            # from the broker in CONTRACTS and must be scaled, or MES at 5x
            # would be understated fivefold.
            "gross_exposure": round(sum(abs(p.get("qty", 0)) * p.get("price", 0)
                                        * p.get("mult", 1.0)
                                        for p in self.positions.values()), 2),
            "net_exposure": round(sum(p.get("qty", 0) * p.get("price", 0)
                                      * p.get("mult", 1.0)
                                      for p in self.positions.values()), 2),
            "positions": self.positions,
            "trades": [asdict(t) for t in reversed(self.trades)],
            "activity": [asdict(a) for a in reversed(self.activity)],
            "curve": self.curve,
        }

    def flush(self) -> None:
        """Atomic write so the dashboard never reads a half-written file."""
        data = json.dumps(self.snapshot(), separators=(",", ":"))
        d = self.path.parent
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
