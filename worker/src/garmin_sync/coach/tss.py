"""TSS (Training Stress Score) calculation with 3-tier strategy.

Tier 1 — Power-based (most precise) : cycling with power-meter + FTP known.
    TSS = duration_h * IF**2 * 100, where IF = power_avg / FTP

Tier 2 — hrTSS : any sport with HR + FCmax known.
    hrTSS = duration_h * IF**2 * 100, where IF = hr_avg / LTHR, LTHR approx 0.90 * FCmax

Tier 3 — Fallback : duration only.
    estTSS = duration_h * 50  (50 TSS/h endurance avg)

All tiers are weighted by ``sports.load_factor`` : non swim/bike/run activities
count at a reduced coefficient (issue #133). Sport labels come from
``coach.sports`` — the single source of truth (issue #120: a local, divergent
cycling list silently killed the power tier for sport='bike').
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from garmin_sync.coach.sports import load_factor, normalize_discipline

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

LTHR_RATIO = 0.90  # LTHR approx 0.90 * FCmax — coarse but standard heuristic
FALLBACK_TSS_PER_HOUR = 50  # average endurance load
FC_MAX_OBSERVATION_DAYS = 90  # window for the observed-hr_max fallback


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
    factor = load_factor(sport)

    # Tier 1 — cycling with power
    if normalize_discipline(sport) == "bike" and power_avg and ftp_watts:
        intensity_factor = power_avg / ftp_watts
        return round(duration_h * intensity_factor**2 * 100 * factor, 2)

    # Tier 2 — hrTSS
    if hr_avg and fc_max_bpm:
        lthr = fc_max_bpm * LTHR_RATIO
        intensity_factor = hr_avg / lthr
        return round(duration_h * intensity_factor**2 * 100 * factor, 2)

    # Tier 3 — fallback
    return round(duration_h * FALLBACK_TSS_PER_HOUR * factor, 2)


def _activity_date(raw_start: Any) -> date | None:
    if not isinstance(raw_start, str):
        return None
    try:
        return datetime.fromisoformat(raw_start.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def resolve_fc_max_bpm(
    profile_fc_max: int | None,
    activities: Iterable[Mapping[str, Any]],
    *,
    today: date,
) -> int | None:
    """FCmax to use for hrTSS: profile value, else observed 90-day max.

    ``athlete_profiles.fc_max_bpm`` is NULL in prod when Garmin's user-settings
    payload carries no usable ``userMaxHr`` (issue #120). Fall back on the max
    ``hr_max`` observed over the last 90 days: the true FCmax is >= any observed
    max, so hrTSS is slightly overestimated — still far better than the flat
    50 TSS/h fallback. Returns None when there is no data at all.
    """
    if profile_fc_max:
        return profile_fc_max
    cutoff = today - timedelta(days=FC_MAX_OBSERVATION_DAYS)
    observed: int | None = None
    for activity in activities:
        hr_max = activity.get("hr_max")
        day = _activity_date(activity.get("start_time"))
        if not hr_max or day is None or day < cutoff:
            continue
        observed = hr_max if observed is None else max(observed, hr_max)
    return observed
