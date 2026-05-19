"""TSS (Training Stress Score) calculation with 3-tier strategy.

Tier 1 — Power-based (most precise) : cycling with power-meter + FTP known.
    TSS = duration_h * IF**2 * 100, where IF = power_avg / FTP

Tier 2 — hrTSS : any sport with HR + FCmax known.
    hrTSS = duration_h * IF**2 * 100, where IF = hr_avg / LTHR, LTHR approx 0.90 * FCmax

Tier 3 — Fallback : duration only.
    estTSS = duration_h * 50  (50 TSS/h endurance avg)
"""

from __future__ import annotations

LTHR_RATIO = 0.90  # LTHR approx 0.90 * FCmax — coarse but standard heuristic
FALLBACK_TSS_PER_HOUR = 50  # average endurance load
CYCLING_SPORTS = {'cycling', 'indoor_cycling', 'mountain_biking'}


def compute_tss(
    *,
    duration_s: int,
    sport: str,
    power_avg: int | None,
    hr_avg: int | None,
    ftp_watts: int | None,
    fc_max_bpm: int | None,
) -> float | None:
    """Compute training stress score for one activity.

    Returns None if duration is invalid (<= 0).
    """
    duration_h = duration_s / 3600
    if duration_h <= 0:
        return None

    # Tier 1 — cycling with power
    if sport in CYCLING_SPORTS and power_avg and ftp_watts:
        intensity_factor = power_avg / ftp_watts
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 2 — hrTSS
    if hr_avg and fc_max_bpm:
        lthr = fc_max_bpm * LTHR_RATIO
        intensity_factor = hr_avg / lthr
        return round(duration_h * intensity_factor**2 * 100, 2)

    # Tier 3 — fallback
    return round(duration_h * FALLBACK_TSS_PER_HOUR, 2)
