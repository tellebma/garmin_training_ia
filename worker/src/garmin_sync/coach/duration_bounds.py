"""Réalisme des durées : bornes plancher/plafond par (discipline, type, phase).

Filet de sécurité déterministe par-dessus le calcul TSS du planner : aucune
séance ne sort en dehors de ces fourchettes (en minutes), calibrées sur les
normes coach triathlon amateur.
"""

from __future__ import annotations

# (low_min, high_min) en MINUTES totales, indexé [discipline][type][phase].
# phase ∈ base/build/peak/taper ; on mappe taper sur la colonne "peak" (volume réduit).
_BOUNDS_MIN: dict[tuple[str, str, str], tuple[int, int]] = {
    # natation
    ("swim", "recovery", "base"): (30, 40),
    ("swim", "endurance", "base"): (45, 60),
    ("swim", "threshold", "base"): (45, 60),
    ("swim", "intervals", "base"): (45, 60),
    ("swim", "long", "base"): (60, 75),
    ("swim", "endurance", "build"): (50, 70),
    ("swim", "threshold", "build"): (50, 70),
    ("swim", "intervals", "build"): (50, 65),
    ("swim", "recovery", "build"): (30, 40),
    ("swim", "long", "build"): (70, 90),
    ("swim", "endurance", "peak"): (40, 55),
    ("swim", "threshold", "peak"): (40, 55),
    ("swim", "intervals", "peak"): (40, 55),
    ("swim", "long", "peak"): (50, 60),
    ("swim", "recovery", "peak"): (25, 35),
    ("swim", "pma", "build"): (40, 55),
    ("swim", "pma", "peak"): (35, 50),
    ("swim", "sprint", "peak"): (30, 40),
    # vélo
    ("bike", "recovery", "base"): (30, 45),
    ("bike", "endurance", "base"): (90, 180),
    ("bike", "threshold", "base"): (60, 90),
    ("bike", "intervals", "base"): (60, 75),
    ("bike", "long", "base"): (120, 210),
    ("bike", "endurance", "build"): (90, 150),
    ("bike", "threshold", "build"): (75, 120),
    ("bike", "intervals", "build"): (60, 90),
    ("bike", "recovery", "build"): (30, 45),
    ("bike", "long", "build"): (150, 240),
    ("bike", "endurance", "peak"): (60, 105),
    ("bike", "threshold", "peak"): (50, 75),
    ("bike", "intervals", "peak"): (50, 70),
    ("bike", "long", "peak"): (90, 150),
    ("bike", "recovery", "peak"): (30, 40),
    ("bike", "pma", "build"): (45, 65),
    ("bike", "pma", "peak"): (40, 60),
    ("bike", "sprint", "peak"): (35, 45),
    # course
    ("run", "recovery", "base"): (30, 40),
    ("run", "endurance", "base"): (40, 60),
    ("run", "threshold", "base"): (40, 55),
    ("run", "intervals", "base"): (45, 60),
    ("run", "long", "base"): (60, 90),
    ("run", "endurance", "build"): (45, 70),
    ("run", "threshold", "build"): (50, 65),
    ("run", "intervals", "build"): (50, 65),
    ("run", "recovery", "build"): (30, 45),
    ("run", "long", "build"): (75, 105),
    ("run", "endurance", "peak"): (35, 50),
    ("run", "threshold", "peak"): (40, 50),
    ("run", "intervals", "peak"): (40, 55),
    ("run", "long", "peak"): (50, 70),
    ("run", "recovery", "peak"): (25, 35),
    ("run", "pma", "build"): (40, 55),
    ("run", "pma", "peak"): (35, 50),
    ("run", "sprint", "peak"): (25, 35),
    # enchaînement vélo->CAP (#154) : une sortie vélo puis 15 à 30 min de course
    ("brick", "endurance", "base"): (60, 120),
    ("brick", "endurance", "build"): (70, 150),
    ("brick", "endurance", "peak"): (60, 120),
    ("brick", "long", "base"): (90, 150),
    ("brick", "long", "build"): (100, 180),
    ("brick", "long", "peak"): (90, 150),
}


def _phase_key(phase: str) -> str:
    """Taper partage les bornes réduites de peak."""
    return "peak" if phase == "taper" else phase


def duration_bounds_s(sport: str, stype: str, phase: str) -> tuple[int, int] | None:
    """Bornes (low, high) en SECONDES, ou None si le combo n'est pas borné."""
    bounds = _BOUNDS_MIN.get((sport, stype, _phase_key(phase)))
    if bounds is None:
        return None
    low, high = bounds
    return low * 60, high * 60


def clamp_duration_to_bounds(sport: str, stype: str, phase: str, duration_s: int) -> int:
    """Ramène duration_s dans la fourchette réaliste. Inchangé si non borné."""
    bounds = duration_bounds_s(sport, stype, phase)
    if bounds is None:
        return duration_s
    low, high = bounds
    return max(low, min(high, duration_s))
