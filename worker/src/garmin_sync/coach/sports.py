"""Mapping Garmin sport label -> training discipline (swim / bike / run).

Single source of truth, shared by coach modules that need to bucket activities
by discipline.
"""

from __future__ import annotations

DISCIPLINE_SPORTS: dict[str, set[str]] = {
    "swim": {"swim", "swimming", "lap_swimming", "open_water_swimming"},
    "bike": {"bike", "cycling", "indoor_cycling", "mountain_biking"},
    "run": {"run", "running", "trail_running", "treadmill_running"},
}

_SPORT_TO_DISCIPLINE: dict[str, str] = {
    sport: discipline for discipline, sports in DISCIPLINE_SPORTS.items() for sport in sports
}


def normalize_discipline(sport: str) -> str | None:
    """Return 'swim' | 'bike' | 'run' for a Garmin sport label, else None."""
    return _SPORT_TO_DISCIPLINE.get(sport)


# Decision for issue #133 (option b — reduced coefficient, not exclusion):
# a 3 h 30 hike produces real fatigue that must appear in ATL/TSB — excluding it
# entirely (option a) would let the coach schedule a hard session right after.
# But it is non-specific load: counting it at full price inflates CTL and fires
# false load_spike alerts. 0.5 is a deliberately conservative middle ground,
# to recalibrate once we have enough non-discipline activities in prod.
NON_DISCIPLINE_LOAD_FACTOR = 0.5


def load_factor(sport: str) -> float:
    """Weight of a sport in the training-load (TSS → CTL/ATL) computation.

    1.0 for the race disciplines (swim/bike/run), NON_DISCIPLINE_LOAD_FACTOR
    for everything else (hiking, strength_training, yoga, ...).
    """
    return 1.0 if normalize_discipline(sport) else NON_DISCIPLINE_LOAD_FACTOR
