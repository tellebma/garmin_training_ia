"""Tests for Banister exponential model (CTL/ATL/TSB)."""

from __future__ import annotations

from datetime import date, timedelta

from garmin_sync.coach.banister import (
    ATL_TAU,
    COLD_START_MIN_ACTIVITY_DAYS,
    CTL_TAU,
    cold_start_state,
    compute_banister_history,
    estimate_initial_ctl_from_profile,
    is_cold_start,
)


def test_constants_match_classic_model() -> None:
    assert CTL_TAU == 42
    assert ATL_TAU == 7


def test_compute_banister_zero_tss_decays_exponentially() -> None:
    """No TSS for 42 days → CTL decays exponentially."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=41)  # 42 days inclusive
    states = compute_banister_history({}, start, end, initial_ctl=100.0, initial_atl=100.0)
    assert len(states) == 42
    final = states[-1]
    # Analytic : ctl_n = ctl_0 * (1 - 1/tau)^n
    expected_ctl = 100.0 * (1 - 1 / CTL_TAU) ** 42
    assert abs(final.ctl - expected_ctl) < 0.5


def test_compute_banister_constant_tss_converges() -> None:
    """TSS=100 every day for 200 days → CTL converges towards 100."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=199)
    tss_dict = {start + timedelta(days=i): 100.0 for i in range(200)}
    states = compute_banister_history(tss_dict, start, end, initial_ctl=0.0, initial_atl=0.0)
    final = states[-1]
    assert final.ctl > 99.0
    assert final.atl > 99.0
    assert abs(final.tsb) < 1.0


def test_compute_banister_single_day() -> None:
    """start = end → 1 state returned."""
    start = date(2026, 1, 1)
    states = compute_banister_history({start: 50.0}, start, start, initial_ctl=0.0, initial_atl=0.0)
    assert len(states) == 1
    # ctl_0=0, tss=50 → ctl_1 = (50-0)/42 ≈ 1.19
    assert abs(states[0].ctl - 50.0 / CTL_TAU) < 0.01


def test_compute_banister_missing_days_treated_as_zero() -> None:
    """Gaps in tss_by_date are zero TSS (rest days)."""
    start = date(2026, 1, 1)
    end = start + timedelta(days=2)
    tss_dict = {start: 100.0}  # only day 0
    states = compute_banister_history(tss_dict, start, end, initial_ctl=0.0, initial_atl=0.0)
    assert len(states) == 3
    assert states[0].ctl > states[1].ctl > states[2].ctl


def test_estimate_initial_ctl_from_profile_realistic() -> None:
    """hours_per_week=8 → ~57 TSS daily-equivalent baseline."""
    assert estimate_initial_ctl_from_profile(8) == round(8 * 50 / 7, 2)


def test_estimate_initial_ctl_from_profile_zero_or_none() -> None:
    assert estimate_initial_ctl_from_profile(None) == 0.0
    assert estimate_initial_ctl_from_profile(0) == 0.0


def test_is_cold_start_threshold() -> None:
    """#134: cold start = strictly fewer than 14 distinct activity days."""
    start = date(2026, 1, 1)
    thirteen = {start + timedelta(days=i): 50.0 for i in range(13)}
    fourteen = {start + timedelta(days=i): 50.0 for i in range(14)}
    assert COLD_START_MIN_ACTIVITY_DAYS == 14
    assert is_cold_start(thirteen) is True
    assert is_cold_start(fourteen) is False
    assert is_cold_start({}) is True


def test_cold_start_state_describes_current_form() -> None:
    """#134: the profile estimate is TODAY's state (ctl=atl=estimate, tsb=0),
    not a seed decaying from 180 days ago."""
    state = cold_start_state(4)
    assert state.ctl == round(4 * 50 / 7, 2)
    assert state.atl == state.ctl
    assert state.tsb == 0.0


def test_cold_start_state_without_profile_hours() -> None:
    state = cold_start_state(None)
    assert state.ctl == 0.0
    assert state.atl == 0.0
    assert state.tsb == 0.0
