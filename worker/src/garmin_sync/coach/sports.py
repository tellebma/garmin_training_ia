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
