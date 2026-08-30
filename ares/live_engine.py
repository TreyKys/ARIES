"""LiveEngine: the deterministic trade loop, one per symbol.

Feed it closed candles via ``step()``. It runs the exact same
Strategy -> risk -> PaperBroker pipeline the backtester uses, so paper
results match backtests. In PAPER mode fills are simulated against real
prices; a future LIVE mode would swap PaperBroker for a real broker
behind the identical decision path.

No LLM on the trigger. No fake data. Every number reported is computed.
"""
from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from . import risk as risk_mod
from .broker import PaperBroker
from .reporting import ConsoleReporter, Reporter
from .risk import AccountState, RiskConfig
from .strategy import Bars, Strategy
from .types import Candle, Costs

_MS_PER_DAY = 86_400_000


class LiveEngine:
    def __init__(self, symbol: str, strategy: Strategy, *,
                 starting_capital: float = 50.0,
                 risk_config: Optional[RiskConfig] = None,
                 costs: Optional[Costs] = None,
                 reporter: Optional[Reporter] = None,
                 ml_model=None, buffer_size: int = 500):
        self.symbol = symbol
        self.strategy = strategy
        self.risk_config = risk_config or RiskConfig()
        self.reporter = reporter or ConsoleReporter()
        self.ml_model = ml_model
        self.broker = PaperBroker(starting_capital, costs)
        self.starting_capital = starting_capital

        self._buf: deque[Candle] = deque(maxlen=buffer_size)
        self.peak_equity = starting_capital
        self.consecutive_losses = 0
        self.cur_day: Optional[int] = None
        self.day_start_equity = starting_capital
        self.total_trades = 0
        self.winning_trades = 0

    def step(self, candle: Candle) -> None:
        """Process one newly-closed candle."""
        self._buf.append(candle)

        day = candle.ts // _MS_PER_DAY
        if day != self.cur_day:
            self.cur_day = day
            self.day_start_equity = self.broker.equity

        # 1. manage an open position against this candle
        trade = self.broker.process(candle)
        if trade is not None:
            self.total_trades += 1
            if trade.pnl > 0:
                self.winning_trades += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
            self.reporter.trade_close({
                "id": getattr(trade, "trade_id", None) or "",
                "exit_price": trade.exit_price, "pnl": trade.pnl,
                "r_multiple": round(trade.r_multiple, 3),
                "closed_at": datetime.now(timezone.utc).isoformat(),
            })
            self.reporter.log("RISK", f"Closed {self.symbol} {trade.reason_close} "
                              f"pnl=${trade.pnl:.4f} ({trade.r_multiple:+.2f}R)",
                              "SUCCESS" if trade.pnl > 0 else "WARN")
            # drawdown peak tracks realised equity (not unrealised spikes)
            self.peak_equity = max(self.peak_equity, self.broker.equity)

        # 2. if flat, ask the deterministic strategy
        if self.broker.flat and len(self._buf) >= getattr(self.strategy, "warmup", 0):
            bars = self._bars()
            fb = self.strategy.prepare(bars)
            if self.ml_model is not None:
                fb.ml_win_prob = self.ml_model.predict_series(fb)
            self._publish_mtf(fb)
            decision = self.strategy.signal_at(fb, len(bars) - 1)
            if decision is not None:
                self._maybe_enter(decision, candle)

        # 3. publish true account state
        self._publish_state(candle.close)

    # --- internals ---------------------------------------------------------
    def _bars(self) -> Bars:
        b = list(self._buf)
        return Bars(
            ts=np.array([c.ts for c in b], dtype=np.int64),
            open=np.array([c.open for c in b]), high=np.array([c.high for c in b]),
            low=np.array([c.low for c in b]), close=np.array([c.close for c in b]),
            volume=np.array([c.volume for c in b]),
        )

    def _maybe_enter(self, decision, candle: Candle) -> None:
        account = AccountState(
            equity=self.broker.equity, peak_equity=self.peak_equity,
            day_start_equity=self.day_start_equity,
            day_pnl=self.broker.equity - self.day_start_equity,
            consecutive_losses=self.consecutive_losses,
        )
        rd = risk_mod.evaluate(account, decision, candle.close, self.risk_config)
        if not rd.approved:
            self.reporter.log("RISK", f"{self.symbol}: stand aside ({rd.reason})", "DEBUG")
            return
        pos = self.broker.open(self.symbol, decision, rd.size, rd.risk_amount,
                               candle.close, candle.ts)
        trade_id = str(uuid.uuid4())
        setattr(pos, "trade_id", trade_id)
        self.reporter.log("STRATEGY", f"ENTER {decision.side.value} {self.symbol} @ "
                          f"{pos.entry_price:.4f} | {decision.reason} | {rd.reason}", "SUCCESS")
        self.reporter.trade_open({
            "id": trade_id, "symbol": self.symbol, "side": decision.side.value,
            "entry_price": pos.entry_price, "stop_loss": decision.stop_price,
            "take_profit": decision.take_profit_price, "status": "OPEN",
            "strategy": type(self.strategy).__name__,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        })

    def _publish_mtf(self, fb) -> None:
        i = len(fb) - 1
        trend = "BULLISH" if fb.ema_fast[i] > fb.ema_slow[i] else "BEARISH"
        self.reporter.mtf(
            macro_bias=trend, macro_trend=trend,
            structure_15m=trend,
            execution_5m="BULLISH" if fb.rsi[i] >= 50 else "BEARISH",
            rsi_5m=round(float(fb.rsi[i]), 1) if not np.isnan(fb.rsi[i]) else None,
        )

    def _publish_state(self, price: float) -> None:
        equity = self.broker.mark_to_market(price)
        win_rate = (self.winning_trades / self.total_trades * 100.0) if self.total_trades else 0.0
        day_pnl = self.broker.equity - self.day_start_equity
        self.reporter.state(
            balance=round(equity, 4),
            today_pnl_abs=round(day_pnl, 4),
            today_pnl_pct=round(day_pnl / self.starting_capital * 100.0, 3),
            win_rate=round(win_rate, 1),
            is_connected=True,
        )
