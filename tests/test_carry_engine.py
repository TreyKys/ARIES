import pytest

from ares.carry_engine import CarryEngine, CarryEngineConfig, merge_funding


def _stream(pair, n, rate, start=1_700_000_000_000, step=8 * 3_600_000):
    return [(start + i * step, 8.0, rate) for i in range(n)]


def test_leverage_scales_funding():
    pairs = ["ETHUSDT"]
    ev = _stream("ETHUSDT", 100, 0.0001)
    e1 = CarryEngine(pairs, 50.0, CarryEngineConfig(leverage=1.0, taker_fee=0.0))
    e2 = CarryEngine(pairs, 50.0, CarryEngineConfig(leverage=2.0, taker_fee=0.0))
    for ts, _h, r in ev:
        e1.on_funding("ETHUSDT", ts, r)
        e2.on_funding("ETHUSDT", ts, r)
    gain1 = e1.equity - 50.0
    gain2 = e2.equity - 50.0
    assert gain2 == pytest.approx(2 * gain1, rel=1e-9)   # 2x leverage -> 2x funding


def test_circuit_breaker_exits_on_deep_negative():
    e = CarryEngine(["ETHUSDT"], 50.0,
                    CarryEngineConfig(leverage=1.0, taker_fee=0.0, neg_funding_exit=-0.0003))
    # deeply negative funding should flip the pair out of market
    for ts, _h, r in _stream("ETHUSDT", 5, -0.001):
        e.on_funding("ETHUSDT", ts, r)
    assert e.pairs["ETHUSDT"].in_market is False


def test_merge_funding_is_time_ordered():
    streams = {"A": _stream("A", 3, 0.0001), "B": _stream("B", 3, 0.0001, start=1_700_000_000_000 + 1)}
    events = merge_funding(streams)
    ts = [e[0] for e in events]
    assert ts == sorted(ts)
    assert len(events) == 6


def test_multi_pair_splits_capital():
    e = CarryEngine(["A", "B"], 50.0, CarryEngineConfig(leverage=2.0))
    # each pair notional = (50/2) * 2 = 50
    assert e.pairs["A"].notional == pytest.approx(50.0)
