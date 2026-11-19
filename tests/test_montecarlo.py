import json
import math

import pytest

from calc.montecarlo import MIN_OBSERVATIONS, compute_return_stats, simulate_gbm
from ingest.price import PriceAccessError, fetch_price_chart, parse_daily_closes


def _closes(n=300, daily=0.0004, wiggle=0.01):
    out, price = [], 100.0
    for i in range(n):
        out.append(price)
        price *= math.exp(daily + (wiggle if i % 2 else -wiggle))
    return out


def test_stats_recover_known_drift_and_vol():
    stats = compute_return_stats(_closes())
    assert stats is not None
    assert stats.n_obs == 299
    assert stats.mu == pytest.approx(0.0004 * 252, abs=0.02)
    assert 0.1 < stats.sigma < 0.4


def test_stats_none_when_too_few_or_invalid():
    assert compute_return_stats(_closes(MIN_OBSERVATIONS)) is None
    assert compute_return_stats(_closes() + [0.0]) is None
    assert compute_return_stats(_closes() + [float("nan")]) is None


def test_simulation_is_seeded_and_matches_theory():
    a = simulate_gbm(s0=100, mu=0.1, sigma=0.2, days=252, n_paths=4000, seed=1)
    assert a == simulate_gbm(s0=100, mu=0.1, sigma=0.2, days=252, n_paths=4000, seed=1)
    mean = sum(a) / len(a)
    assert mean == pytest.approx(100 * math.exp(0.1), rel=0.03)  # E[S_T] = S0 e^{mu T}
    assert all(x > 0 for x in a)


def test_zero_vol_is_deterministic():
    finals = simulate_gbm(s0=100, mu=0.1, sigma=0.0, days=252, n_paths=3)
    assert finals[0] == pytest.approx(100 * math.exp(0.1), rel=1e-9)


def test_parse_daily_closes_drops_nulls_and_rejects_garbage():
    raw = json.dumps({"chart": {"result": [{"indicators": {"quote": [{"close": [1.0, None, 2.5]}]}}]}}).encode()
    assert parse_daily_closes(raw) == [1.0, 2.5]
    assert parse_daily_closes(b"no json") is None
    assert parse_daily_closes(b'{"chart": {"result": []}}') is None


def test_fetch_rejects_malformed_ticker():
    with pytest.raises(PriceAccessError):
        fetch_price_chart("AAPL/../../x", history=True)
