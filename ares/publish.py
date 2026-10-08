"""Push the monitor snapshot to the hosted endpoint (Netlify).

Why a push and not a pull: the bot runs on a laptop next to IB Gateway, so a
hosted page has no way to read its state file. The bot sends the snapshot to
netlify/functions/state.mjs, which stores it; the monitor page reads it from
there. That is what makes the dashboard reachable from a phone without
exposing a port at home.

Two rules shape this module:

  1. It NEVER raises. A trading loop must not die because a CDN hiccuped, a
     token expired, or the laptop's wifi dropped. Every failure comes back as
     a string for the caller to log.
  2. It trims. A replay snapshot is ~110KB and most of that is backtest
     history nobody will scroll; a live run pushes every cycle, so the payload
     is cut to what the page actually displays.

Configuration is environment-only -- the write token must never be in source:

    ARIES_STATE_URL=https://<your-site>.netlify.app/api/state
    ARIES_WRITE_TOKEN=<the same value set in the Netlify UI>
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# Caps for the pushed payload. The page shows a few screens of history, not
# the whole run; the local state file keeps the full record.
PUSH_TRADES = 200
PUSH_ACTIVITY = 150
PUSH_CURVE = 600
MAX_BYTES = 4_000_000


def trim(snap: Dict[str, Any], *, trades: int = PUSH_TRADES,
         activity: int = PUSH_ACTIVITY, curve: int = PUSH_CURVE
         ) -> Dict[str, Any]:
    """Shrink a snapshot to what the page displays, keeping the newest rows.

    Trades and activity arrive newest-first, so a head slice keeps the recent
    ones. The equity curve is chronological and must keep its SHAPE, so it is
    decimated evenly rather than truncated -- a head slice would show the
    start of the run and hide the present, and a tail slice would silently
    rescale the drawdown the page draws.
    """
    out = dict(snap)
    out["trades"] = list(snap.get("trades") or [])[:trades]
    out["activity"] = list(snap.get("activity") or [])[:activity]
    c = list(snap.get("curve") or [])
    if len(c) > curve > 0:
        step = len(c) / curve
        kept = [c[int(i * step)] for i in range(curve)]
        if kept[-1] != c[-1]:
            kept[-1] = c[-1]          # the latest point is never dropped
        out["curve"] = kept
    else:
        out["curve"] = c
    out["truncated"] = len(out["trades"]) < len(snap.get("trades") or [])
    return out


class Publisher:
    """Posts snapshots to ARIES_STATE_URL. Returns errors, never raises."""

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None,
                 min_interval: float = 10.0, timeout: float = 8.0,
                 opener=None):
        self.url = (url if url is not None
                    else os.environ.get("ARIES_STATE_URL", "")).strip()
        self.token = (token if token is not None
                      else os.environ.get("ARIES_WRITE_TOKEN", "")).strip()
        self.min_interval = min_interval
        self.timeout = timeout
        # Injectable so tests exercise the real request-building path without
        # touching the network.
        self._open = opener or urllib.request.urlopen
        # None, not 0.0: time.monotonic()'s zero point is arbitrary (uptime on
        # Linux), so comparing against 0.0 skipped every push during the first
        # min_interval seconds of machine uptime.
        self._last: Optional[float] = None
        self.pushes = 0
        self.failures = 0

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    def why_disabled(self) -> str:
        if not self.url:
            return "ARIES_STATE_URL is not set"
        if not self.token:
            return "ARIES_WRITE_TOKEN is not set"
        return ""

    def __call__(self, snap: Dict[str, Any]) -> Optional[str]:
        """Monitor calls the publisher directly; same contract as push()."""
        return self.push(snap)

    def push(self, snap: Dict[str, Any], force: bool = False) -> Optional[str]:
        """Send a snapshot. Returns None on success, else an error string.

        Rate-limited: a replay flushes hundreds of times and a live loop
        flushes every cycle, neither of which needs to leave the machine that
        often. force=True overrides it for the final snapshot of a run, which
        is the one that must land.
        """
        if not self.enabled:
            return None                      # hosting is opt-in, not an error
        now = time.monotonic()
        if (not force and self._last is not None
                and (now - self._last) < self.min_interval):
            return None
        self._last = now
        try:
            body = json.dumps(trim(snap), separators=(",", ":")).encode()
        except (TypeError, ValueError) as e:
            self.failures += 1
            return f"snapshot is not serialisable: {e}"
        if len(body) > MAX_BYTES:
            self.failures += 1
            return f"snapshot too large to publish ({len(body)} bytes)"
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {self.token}"})
        try:
            with self._open(req, timeout=self.timeout) as r:
                code = getattr(r, "status", None) or r.getcode()
            if code not in (200, 201, 202, 204):
                self.failures += 1
                return f"publish returned HTTP {code}"
            self.pushes += 1
            return None
        except urllib.error.HTTPError as e:
            self.failures += 1
            hint = {401: " -- ARIES_WRITE_TOKEN does not match the site",
                    404: " -- is /api/state deployed?",
                    503: " -- the site has no ARIES_WRITE_TOKEN set"}.get(e.code, "")
            return f"publish failed HTTP {e.code}{hint}"
        except Exception as e:                            # noqa: BLE001
            # urllib raises a wide family here (URLError, socket.timeout, OSError,
            # ssl errors). None of them may reach the trading loop.
            self.failures += 1
            return f"publish failed: {type(e).__name__}: {e}"
