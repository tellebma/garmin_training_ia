from __future__ import annotations

import pytest

from garmin_sync import strava_rate_limit as rl


@pytest.fixture(autouse=True)
def _reset_state():
    rl._calls_15min.clear()
    rl._calls_daily.clear()
    yield
    rl._calls_15min.clear()
    rl._calls_daily.clear()


def test_check_or_raise_allows_under_limit():
    for _ in range(5):
        rl.check_or_raise()
        rl.record_call()
    # no exception


def test_check_or_raise_blocks_over_15min_limit():
    for _ in range(rl._MAX_PER_15MIN):
        rl.record_call()
    with pytest.raises(rl.StravaRateLimitExceeded):
        rl.check_or_raise()


def test_check_or_raise_blocks_over_daily_limit(monkeypatch):
    monkeypatch.setattr(rl, "_MAX_PER_15MIN", 10_000)
    for _ in range(rl._MAX_PER_DAY):
        rl.record_call()
    with pytest.raises(rl.StravaRateLimitExceeded):
        rl.check_or_raise()
