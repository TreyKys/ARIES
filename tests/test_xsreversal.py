import numpy as np
import pandas as pd

from ares.ledger import summarise
from ares.xsreversal import breakeven_cost_bps, run_xs_reversal


def _synth(n=3000, k=10, revert=0.0, seed=1):
    """Common market factor plus an idiosyncratic part with chosen reversion.

    revert > 0: the previous idiosyncratic move partly reverses -> a real edge.
    revert < 0: it continues (momentum) -> a reversal strategy must LOSE.
    revert = 0: pure random walk -> no edge.
    """
    g = np.random.default_rng(seed)
    mkt = g.normal(0, 0.01, n)
    e = g.normal(0, 0.01, (n, k))
    idio = np.zeros((n, k))
    for t in range(1, n):
        idio[t] = e[t] - revert * e[t - 1]
    px = 100 * np.cumprod(1 + mkt[:, None] + idio, axis=0)
    return pd.DataFrame(px, index=pd.date_range("2021-01-01", periods=n, freq="1h"),
                        columns=[f"C{i}" for i in range(k)])


def test_profits_when_idiosyncratic_moves_revert():
    r = run_xs_reversal(_synth(revert=0.5), top_k=3, cost_bps=0.0)
    assert r.gross_return_pct > 0
    assert summarise(r.ledger, periods_per_year=24 * 365).sharpe > 1.0


def test_loses_when_idiosyncratic_moves_trend():
    # If divergences continue instead of snapping back, betting on reversal
    # must lose. Guards against a sign error making any input look profitable.
    r = run_xs_reversal(_synth(revert=-0.4), top_k=3, cost_bps=0.0)
    assert summarise(r.ledger, periods_per_year=24 * 365).sharpe < 0


def test_flat_on_a_pure_random_walk():
    """No edge in, no edge out -- asserted on the MEAN over seeds, not one path.

    Sharpe measurement error depends on elapsed YEARS, not on bet count: a fast
    strategy makes more bets (raising its TRUE Sharpe) without shrinking the
    error per unit time. Over 3,000 hourly bars (~4 months) single-path Sharpe
    on a no-edge series ranged -4.56..+4.49 across seeds, sd 2.49, so a
    single-path bound here would be testing the random seed.
    """
    vals = []
    for seed in range(12):
        r = run_xs_reversal(_synth(revert=0.0, seed=seed), top_k=3, cost_bps=0.0)
        vals.append(summarise(r.ledger, periods_per_year=24 * 365).sharpe)
    mean = float(np.mean(vals))
    stderr = float(np.std(vals)) / np.sqrt(len(vals))
    assert abs(mean) < 3.0 * max(stderr, 1e-9)      # indistinguishable from zero


def test_book_is_dollar_neutral():
    px = _synth(revert=0.3)
    r = run_xs_reversal(px, top_k=3, cost_bps=0.0)
    led = r.ledger
    gross = led.gross_exposure()
    assert gross > 0
    # long and short legs sized equally -> net exposure is a rounding residue
    assert abs(led.net_exposure()) < 0.02 * gross


def test_costs_scale_with_turnover_and_reduce_return():
    px = _synth(revert=0.5)
    free = run_xs_reversal(px, top_k=3, cost_bps=0.0)
    paid = run_xs_reversal(px, top_k=3, cost_bps=5.0)
    assert paid.fees_paid > 0
    assert paid.ledger.equity() < free.ledger.equity()


def test_longer_hold_cuts_the_fee_bill():
    """Turnover scales with bet count, which is why a fast strategy lives or
    dies on cost: hourly repositioning traded ~13,500x capital per year."""
    px = _synth(revert=0.4)
    fast = run_xs_reversal(px, hold=1, top_k=3, cost_bps=5.0)
    slow = run_xs_reversal(px, hold=24, top_k=3, cost_bps=5.0)
    assert slow.fees_paid < fast.fees_paid
    assert slow.n_rebalances < fast.n_rebalances


def test_ruin_reports_a_rate_not_nan():
    # equity through zero must not yield NaN, which would silently poison a
    # results table instead of failing visibly
    r = run_xs_reversal(_synth(revert=-0.9), top_k=4, cost_bps=20.0)
    assert not np.isnan(r.gross_return_pct)


def test_breakeven_cost_is_positive_when_an_edge_exists():
    be = breakeven_cost_bps(_synth(revert=0.5), top_k=3)
    assert be > 0
