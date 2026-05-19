"""Tests for TSS calculation (multi-tier: power > hrTSS > duration fallback)."""

from __future__ import annotations

from garmin_sync.coach.tss import compute_tss


def test_cycling_with_power_uses_pwTSS_formula() -> None:
    """TSS = duration_h * IF**2 * 100 where IF = power_avg / FTP."""
    tss = compute_tss(
        duration_s=3600,  # 1h
        sport='cycling',
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
        sport='running',
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
        sport='swimming',
        power_avg=None,
        hr_avg=None,
        ftp_watts=None,
        fc_max_bpm=None,
    )
    # 2h * 50 = 100
    assert tss == 100.0


def test_zero_duration_returns_none() -> None:
    assert compute_tss(
        duration_s=0,
        sport='cycling',
        power_avg=200,
        hr_avg=150,
        ftp_watts=250,
        fc_max_bpm=180,
    ) is None


def test_cycling_without_power_falls_back_to_hrTSS() -> None:
    """If sport is cycling but no power_avg, use hrTSS not fallback."""
    tss = compute_tss(
        duration_s=3600,
        sport='cycling',
        power_avg=None,
        hr_avg=144,  # = 0.8 * 180
        ftp_watts=None,
        fc_max_bpm=180,
    )
    # LTHR = 162, IF = 144/162 ≈ 0.889 → TSS ≈ 79
    assert tss is not None
    assert 78 < tss < 80
