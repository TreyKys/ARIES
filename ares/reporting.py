"""Reporters: where the engine publishes its true state.

Two implementations share one interface:

- ``ConsoleReporter``  : prints (local dry-runs, CI, geo-blocked hosts).
- ``SupabaseReporter`` : writes the SAME tables the React dashboard reads
  (system_state, council_feed, signals, trades, mtf_analysis), so the UI
  shows real engine state -- no hardcoded 85%, no random sentiment.

Everything written here is computed from real data. If a value isn't
real, it isn't published.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol

logger = logging.getLogger("ares.report")


class Reporter(Protocol):
    def log(self, agent: str, message: str, severity: str = "INFO") -> None: ...
    def state(self, **fields) -> None: ...
    def signal(self, **fields) -> None: ...
    def mtf(self, **fields) -> None: ...
    def trade_open(self, trade: dict) -> None: ...
    def trade_close(self, trade: dict) -> None: ...


class ConsoleReporter:
    def log(self, agent: str, message: str, severity: str = "INFO") -> None:
        logger.info("[%s] %s", agent, message)

    def state(self, **fields) -> None:
        logger.info("STATE %s", {k: fields[k] for k in ("balance", "day_pnl", "win_rate") if k in fields})

    def signal(self, **fields) -> None:
        logger.info("SIGNAL %s", fields)

    def mtf(self, **fields) -> None:
        logger.debug("MTF %s", fields)

    def trade_open(self, trade: dict) -> None:
        logger.info("OPEN  %s %s @ %.4f", trade.get("side"), trade.get("symbol"), trade.get("entry_price", 0))

    def trade_close(self, trade: dict) -> None:
        logger.info("CLOSE %s %s pnl=%.4f", trade.get("side"), trade.get("symbol"), trade.get("pnl", 0))


class SupabaseReporter:
    """Writes real engine state to Supabase. Falls back to no-op on error
    so a reporting hiccup never crashes the trading loop."""

    def __init__(self, url: str, key: str):
        from supabase import create_client  # lazy: only needed on the VPS
        self.client = create_client(url, key)

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            logger.debug("supabase write failed: %s", e)

    def log(self, agent: str, message: str, severity: str = "INFO") -> None:
        self._safe(lambda: self.client.table("council_feed").insert(
            {"agent_name": agent, "message": message, "severity": severity}).execute())

    def state(self, **fields) -> None:
        self._safe(lambda: self.client.table("system_state").update(fields).eq("id", 1).execute())

    def signal(self, **fields) -> None:
        self._safe(lambda: self.client.table("signals").insert(fields).execute())

    def mtf(self, **fields) -> None:
        self._safe(lambda: self.client.table("mtf_analysis").update(fields).eq("id", 1).execute())

    def trade_open(self, trade: dict) -> None:
        self._safe(lambda: self.client.table("trades").insert(trade).execute())

    def trade_close(self, trade: dict) -> None:
        self._safe(lambda: self.client.table("trades").update(
            {"exit_price": trade["exit_price"], "pnl_usd": trade["pnl"],
             "r_multiple": trade["r_multiple"], "status": "CLOSED",
             "closed_at": trade["closed_at"]}).eq("id", trade["id"]).execute())
