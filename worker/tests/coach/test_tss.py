"""Tests for TSS calculation (multi-tier: power > hrTSS > duration fallback)."""

from __future__ import annotations

from datetime import date

from garmin_sync.coach.tss import compute_tss, resolve_fc_max_bpm


def test_cycling_with_power_uses_pwTSS_formula() -> None:
    """TSS = duration_h * IF**2 * 100 where IF = power_avg / FTP."""
    tss = compute_tss(
        duration_s=3600,  # 1h
        sport="cycling",
        power_avg=200,
        hr_avg=None,
        ftp_watts=250,
        fc_max_bpm=None,
    )
    # IF = 200/250 = 0.8 → TSS = 1 * 0.64 * 100 = 64
    assert tss == 64.0


def test_running_with_hr_uses_hrTSS() -> None:
    """hrTSS = duration_h * IF**2 * 100 where IF = hr_avg / (0.9 * FCmax)."""
    tss = compute_tss(
        duration_s=3600,
        sport="running",
        power_avg=None,
        hr_avg=153,  # = 0.9 * 170 (LTHR if FCmax=170)
        ftp_watts=None,
        fc_max_bpm=170,
    )
    # IF = 153/(0.9 * 170) = 153/153 = 1.0 -> TSS = 1 * 1 * 100 = 100
    assert tss == 100.0


def test_duration_only_fallback() -> None:
    """No power, no HR → 50 TSS/h fallback."""
    tss = compute_tss(
        duration_s=7200,  # 2h
        sport="swimming",
        power_avg=None,
        hr_avg=None,
        ftp_watts=None,
        fc_max_bpm=None,
    )
    # 2h * 50 = 100
    assert tss == 100.0


def test_zero_duration_returns_none() -> None:
    assert (
        compute_tss(
            duration_s=0,
            sport="cycling",
            power_avg=200,
            hr_avg=150,
            ftp_watts=250,
            fc_max_bpm=180,
        )
        is None
    )


def test_bike_db_label_with_power_uses_power_tier() -> None:
    """#120: activities are stored with sport='bike' — the power tier must apply."""
    tss = compute_tss(
        duration_s=3600,
        sport="bike",
        power_avg=200,
        hr_avg=150,
        ftp_watts=250,
        fc_max_bpm=180,
    )
    # IF = 200/250 = 0.8 → TSS = 1 * 0.64 * 100 = 64 (power tier, not hrTSS)
    assert tss == 64.0


def test_same_duration_different_hr_produce_different_tss() -> None:
    """#120 key regression: two same-duration activities at very different HR
    must NOT cost the same — the audit found 100% of prod activities at 50 TSS/h."""
    easy = compute_tss(
        duration_s=3600,
        sport="run",
        power_avg=None,
        hr_avg=120,
        ftp_watts=None,
        fc_max_bpm=190,
    )
    hard = compute_tss(
        duration_s=3600,
        sport="run",
        power_avg=None,
        hr_avg=175,
        ftp_watts=None,
        fc_max_bpm=190,
    )
    assert easy is not None
    assert hard is not None
    assert hard > easy


def test_non_discipline_sport_counts_at_reduced_factor() -> None:
    """#133 (option b): hiking counts at half its raw hrTSS — real fatigue, but
    non-specific load."""
    hike = compute_tss(
        duration_s=3600,
        sport="hiking",
        power_avg=None,
        hr_avg=153,
        ftp_watts=None,
        fc_max_bpm=170,
    )
    run = compute_tss(
        duration_s=3600,
        sport="running",
        power_avg=None,
        hr_avg=153,
        ftp_watts=None,
        fc_max_bpm=170,
    )
    assert run == 100.0
    assert hike == 50.0  # 100 * 0.5


def test_non_discipline_fallback_tier_also_reduced() -> None:
    """#133: strength_training without HR → duration fallback * 0.5."""
    tss = compute_tss(
        duration_s=7200,
        sport="strength_training",
        power_avg=None,
        hr_avg=None,
        ftp_watts=None,
        fc_max_bpm=None,
    )
    # 2h * 50 * 0.5 = 50
    assert tss == 50.0


def test_resolve_fc_max_prefers_profile_value() -> None:
    fc = resolve_fc_max_bpm(
        188,
        [{"start_time": "2026-07-30T08:00:00Z", "hr_max": 201}],
        today=date(2026, 8, 1),
    )
    assert fc == 188


def test_resolve_fc_max_falls_back_to_observed_90d_max() -> None:
    """#120: fc_max_bpm NULL in prod → use max observed hr_max over 90 days."""
    activities = [
        {"start_time": "2026-07-30T08:00:00Z", "hr_max": 172},
        {"start_time": "2026-06-15T08:00:00Z", "hr_max": 185},
        {"start_time": "2026-01-01T08:00:00Z", "hr_max": 199},  # > 90 d → ignored
        {"start_time": "2026-07-01T08:00:00Z", "hr_max": None},
        {"start_time": None, "hr_max": 250},
    ]
    assert resolve_fc_max_bpm(None, activities, today=date(2026, 8, 1)) == 185


def test_resolve_fc_max_returns_none_without_any_data() -> None:
    assert resolve_fc_max_bpm(None, [], today=date(2026, 8, 1)) is None


def test_cycling_without_power_falls_back_to_hrTSS() -> None:
    """If sport is cycling but no power_avg, use hrTSS not fallback."""
    tss = compute_tss(
        duration_s=3600,
        sport="cycling",
        power_avg=None,
        hr_avg=144,  # = 0.8 * 180
        ftp_watts=None,
        fc_max_bpm=180,
    )
    # LTHR = 162, IF = 144/162 ≈ 0.889 → TSS ≈ 79
    assert tss is not None
    assert 78 < tss < 80


def test_brick_activity_counts_at_full_load() -> None:
    """#169: a brick / multi_sport is race-specific work, not a hike — it must
    not be discounted by NON_DISCIPLINE_LOAD_FACTOR."""
    brick = compute_tss(
        duration_s=3600,
        sport="multi_sport",
        power_avg=None,
        hr_avg=153,
        ftp_watts=None,
        fc_max_bpm=170,
    )
    assert brick == 100.0
