"""Mapping Garmin sport label -> training discipline (swim / bike / run / brick).

Single source of truth, shared by coach modules that need to bucket activities
by discipline.
"""

from __future__ import annotations

# Enchaînement vélo->course (issue #169). Garmin étiquette ces séances
# `multi_sport` ou `transition` ; `brick`/`triathlon`/`duathlon` couvrent les
# imports d'autres sources. C'est la séance la PLUS spécifique d'une prépa
# triathlon : elle n'a rien à faire dans le fourre-tout non-discipline.
BRICK_SPORTS: set[str] = {
    "brick",
    "multi_sport",
    "multisport",
    "transition",
    "triathlon",
    "duathlon",
}

DISCIPLINE_SPORTS: dict[str, set[str]] = {
    "swim": {"swim", "swimming", "lap_swimming", "open_water_swimming"},
    "bike": {"bike", "cycling", "indoor_cycling", "mountain_biking"},
    "run": {"run", "running", "trail_running", "treadmill_running"},
    "brick": BRICK_SPORTS,
}

# Les trois disciplines de l'épreuve : ce que l'athlète déclare, ce que le plan
# alloue. `brick` est une discipline d'ENTRAÎNEMENT, pas une discipline de course.
CORE_DISCIPLINES: tuple[str, str, str] = ("swim", "bike", "run")

# Un enchaînement entraîne réellement les deux disciplines qu'il enchaîne.
_BRICK_CONTRIBUTIONS: set[str] = {"bike", "run"}

# ... mais son D+ est encaissé quasi intégralement sur la partie vélo. L'attribuer
# aussi à la course le compterait deux fois et gonflerait la rampe de D+ course.
_BRICK_ELEVATION_DISCIPLINE = "bike"

_SPORT_TO_DISCIPLINE: dict[str, str] = {
    sport: discipline for discipline, sports in DISCIPLINE_SPORTS.items() for sport in sports
}


def normalize_discipline(sport: str) -> str | None:
    """Return 'swim' | 'bike' | 'run' | 'brick' for a Garmin sport label, else None."""
    return _SPORT_TO_DISCIPLINE.get(sport)


def contributing_disciplines(sport: str) -> set[str]:
    """Core disciplines actually trained by this sport.

    A brick trains both bike and run, so it must feed both buckets when counting
    volume or regularity per discipline (#169). A non-discipline sport feeds none.
    """
    discipline = normalize_discipline(sport)
    if discipline is None:
        return set()
    if discipline == "brick":
        return set(_BRICK_CONTRIBUTIONS)
    return {discipline}


def elevation_discipline(sport: str) -> str | None:
    """Discipline to credit this activity's elevation gain to, if any.

    Same as ``normalize_discipline`` except for bricks, whose D+ is credited to
    the bike leg only — see ``_BRICK_ELEVATION_DISCIPLINE``.
    """
    discipline = normalize_discipline(sport)
    if discipline == "brick":
        return _BRICK_ELEVATION_DISCIPLINE
    return discipline


# Decision for issue #133 (option b — reduced coefficient, not exclusion):
# a 3 h 30 hike produces real fatigue that must appear in ATL/TSB — excluding it
# entirely (option a) would let the coach schedule a hard session right after.
# But it is non-specific load: counting it at full price inflates CTL and fires
# false load_spike alerts. 0.5 is a deliberately conservative middle ground,
# to recalibrate once we have enough non-discipline activities in prod.
NON_DISCIPLINE_LOAD_FACTOR = 0.5


def load_factor(sport: str) -> float:
    """Weight of a sport in the training-load (TSS → CTL/ATL) computation.

    1.0 for the race disciplines (swim/bike/run) and for bricks (#169),
    NON_DISCIPLINE_LOAD_FACTOR for everything else (hiking, strength_training,
    yoga, ...).
    """
    return 1.0 if normalize_discipline(sport) else NON_DISCIPLINE_LOAD_FACTOR
