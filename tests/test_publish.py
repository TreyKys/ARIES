"""Tests for the snapshot publisher.

The publisher sits in the trading loop's path, so the contract under test is
narrow and absolute: it must never raise, it must not leak the token into a
message, and it must not mangle the equity curve while shrinking it.
"""
import json
import urllib.error

import pytest

from ares.monitor import Monitor
from ares.publish import MAX_BYTES, Publisher, trim


class FakeResponse:
    def __init__(self, status=204):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def recorder(status=204):
    """An opener that captures the request instead of sending it."""
    seen = {}

    def _open(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data.decode())
        seen["timeout"] = timeout
        return FakeResponse(status)

    return _open, seen


# --- trim ------------------------------------------------------------------

def test_trim_keeps_newest_trades():
    snap = {"trades": [{"i": i} for i in range(500)],       # newest first
            "activity": [{"i": i} for i in range(400)],
            "curve": []}
    out = trim(snap, trades=10, activity=5, curve=0)
    assert out["trades"] == [{"i": i} for i in range(10)]
    assert out["activity"] == [{"i": i} for i in range(5)]
    assert out["truncated"] is True


def test_trim_decimates_the_curve_but_keeps_both_ends():
    curve = [[i, 1000.0 + i] for i in range(5000)]
    out = trim({"curve": curve}, curve=100)
    assert len(out["curve"]) == 100
    # Both ends must survive: the first point sets the left edge of the chart
    # and the last IS the current equity. A head or tail slice loses one.
    assert out["curve"][0] == curve[0]
    assert out["curve"][-1] == curve[-1]
    # and it must stay in order, or the sparkline draws a zigzag
    xs = [p[0] for p in out["curve"]]
    assert xs == sorted(xs)


def test_trim_leaves_a_short_curve_alone():
    curve = [[i, float(i)] for i in range(10)]
    assert trim({"curve": curve}, curve=600)["curve"] == curve
    assert trim({"curve": curve}, curve=600)["truncated"] is False


def test_trim_does_not_mutate_the_original():
    snap = {"trades": [{"i": i} for i in range(5)], "curve": [], "equity": 1.0}
    trim(snap, trades=1)
    assert len(snap["trades"]) == 5


# --- enablement ------------------------------------------------------------

def test_disabled_without_configuration_and_that_is_not_an_error():
    p = Publisher(url="", token="")
    assert not p.enabled
    # Hosting is opt-in. An unconfigured publisher returns None, not a warning
    # the user would see on every flush of a purely local run.
    assert p.push({"equity": 1}) is None
    assert "ARIES_STATE_URL" in p.why_disabled()


def test_missing_token_is_named_specifically():
    assert "ARIES_WRITE_TOKEN" in Publisher(url="https://x/api/state",
                                            token="").why_disabled()


def test_reads_configuration_from_the_environment(monkeypatch):
    monkeypatch.setenv("ARIES_STATE_URL", "https://site/api/state")
    monkeypatch.setenv("ARIES_WRITE_TOKEN", "tok")
    p = Publisher()
    assert p.enabled and p.url == "https://site/api/state"


# --- the request itself ----------------------------------------------------

def test_posts_bearer_token_and_json_body():
    op, seen = recorder()
    p = Publisher(url="https://site/api/state", token="secret", opener=op)
    assert p.push({"equity": 25_000.0, "trades": [], "curve": []}) is None
    assert seen["method"] == "POST"
    assert seen["headers"]["authorization"] == "Bearer secret"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["body"]["equity"] == 25_000.0
    assert p.pushes == 1


def test_rate_limited_until_forced():
    op, seen = recorder()
    p = Publisher(url="https://s/api/state", token="t", min_interval=3600,
                  opener=op)
    assert p.push({"a": 1}) is None
    assert p.push({"a": 2}) is None          # inside the window: skipped
    assert p.pushes == 1
    assert p.push({"a": 3}, force=True) is None
    assert p.pushes == 2
    assert seen["body"]["a"] == 3


@pytest.mark.parametrize("exc,expect", [
    (urllib.error.HTTPError("u", 401, "no", {}, None), "ARIES_WRITE_TOKEN"),
    (urllib.error.HTTPError("u", 404, "no", {}, None), "/api/state"),
    (urllib.error.HTTPError("u", 503, "no", {}, None), "ARIES_WRITE_TOKEN"),
    (urllib.error.URLError("dns went away"), "publish failed"),
    (TimeoutError("timed out"), "TimeoutError"),
    (OSError("network is unreachable"), "OSError"),
])
def test_every_failure_comes_back_as_a_string_never_an_exception(exc, expect):
    def boom(req, timeout=None):
        raise exc
    p = Publisher(url="https://s/api/state", token="t", opener=boom)
    err = p.push({"a": 1})                   # must not raise
    assert err and expect in err
    assert p.failures == 1


def test_error_text_never_contains_the_token():
    def boom(req, timeout=None):
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    p = Publisher(url="https://s/api/state", token="sup3r-s3cret", opener=boom)
    assert "sup3r-s3cret" not in (p.push({"a": 1}) or "")


def test_unexpected_status_is_reported():
    op, _ = recorder(status=500)
    p = Publisher(url="https://s/api/state", token="t", opener=op)
    assert "HTTP 500" in (p.push({"a": 1}) or "")


def test_unserialisable_snapshot_is_reported_not_raised():
    op, _ = recorder()
    p = Publisher(url="https://s/api/state", token="t", opener=op)
    assert "not serialisable" in (p.push({"bad": object()}) or "")


def test_oversized_snapshot_is_refused_before_sending():
    sent = []

    def op(req, timeout=None):
        sent.append(1)
        return FakeResponse()
    p = Publisher(url="https://s/api/state", token="t", opener=op)
    err = p.push({"pad": "x" * (MAX_BYTES + 10), "curve": [], "trades": []})
    assert "too large" in (err or "")
    assert not sent


# --- the monitor's use of it ----------------------------------------------

def test_monitor_flush_publishes_and_still_writes_locally(tmp_path):
    op, seen = recorder()
    p = Publisher(url="https://s/api/state", token="t", min_interval=0,
                  opener=op)
    m = Monitor(path=str(tmp_path / "d.json"), capital=1_000.0, publisher=p)
    m.mark(1_050.0)
    m.flush()
    assert json.loads(m.path.read_text())["equity"] == 1_050.0
    assert seen["body"]["equity"] == 1_050.0


def test_monitor_survives_a_publisher_that_raises(tmp_path):
    def rude(snap, force=False):
        raise RuntimeError("badly written publisher")
    m = Monitor(path=str(tmp_path / "d.json"), capital=1_000.0, publisher=rude)
    m.mark(900.0)
    m.flush()                                  # must not raise
    # the local file is still written, and the failure is visible in the feed
    assert json.loads(m.path.read_text())["equity"] == 900.0
    m.flush()
    assert any(a["level"] == "WARN" and "badly written" in a["message"]
               for a in m.snapshot()["activity"])


def test_publish_errors_are_logged_once_not_every_flush(tmp_path):
    def failing(snap, force=False):
        return "publish failed: offline"
    m = Monitor(path=str(tmp_path / "d.json"), capital=1_000.0,
                publisher=failing)
    for _ in range(20):
        m.mark(1_000.0)
        m.flush()
    warns = [a for a in m.snapshot()["activity"] if a["level"] == "WARN"]
    assert len(warns) == 1, "a long outage must not bury the activity feed"


def test_recovery_is_logged(tmp_path):
    state = {"fail": True}

    def flaky(snap, force=False):
        return "publish failed: offline" if state["fail"] else None
    m = Monitor(path=str(tmp_path / "d.json"), capital=1_000.0, publisher=flaky)
    m.mark(1_000.0); m.flush()
    state["fail"] = False
    m.mark(1_000.0); m.flush()
    m.flush()
    msgs = [a["message"] for a in m.snapshot()["activity"]]
    assert any("publishing again" in x for x in msgs)


def test_flush_can_skip_publishing(tmp_path):
    calls = []

    def pub(snap, force=False):
        calls.append(force)
        return None
    m = Monitor(path=str(tmp_path / "d.json"), capital=1.0, publisher=pub)
    m.flush(publish=False)
    assert calls == []
    m.flush(force_publish=True)
    assert calls == [True]
