from ares.execution import SimBroker, OrderType


def test_post_only_rejects_when_crossing():
    b = SimBroker(maker_fee=0.0002, taker_fee=0.0005)
    ok = b.place("buy", 1.0, 100.0, OrderType.POST_ONLY, maker_fillable=True)
    assert ok.filled and ok.is_maker
    bad = b.place("buy", 1.0, 100.0, OrderType.POST_ONLY, maker_fillable=False)
    assert not bad.filled                      # post-only does NOT cross -> no fill


def test_maker_then_taker_falls_back():
    b = SimBroker(maker_fee=0.0002, taker_fee=0.0005)
    maker = b.place("sell", 2.0, 50.0, OrderType.MAKER_THEN_TAKER, maker_fillable=True)
    assert maker.filled and maker.is_maker
    taker = b.place("sell", 2.0, 50.0, OrderType.MAKER_THEN_TAKER, maker_fillable=False)
    assert taker.filled and not taker.is_maker  # fell back to taker rather than stay unhedged
    assert taker.fee > maker.fee                # taker costs more


def test_taker_always_fills():
    b = SimBroker()
    f = b.place("buy", 1.0, 100.0, OrderType.TAKER, maker_fillable=False)
    assert f.filled and not f.is_maker
