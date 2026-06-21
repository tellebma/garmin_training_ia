"""Disponibilite != entrainement.

``available_days`` est un masque de fenetres possibles. On choisit un sous-ensemble
de jours d'entrainement plafonne par le volume, le niveau et un plancher de repos.
"""

from __future__ import annotations

Level = str  # "beginner" | "intermediate" | "advanced"


def athlete_level(sports_strengths: dict[str, int]) -> Level:
    """Niveau global derive de la moyenne des notes 1-5 par discipline."""
    scores = [sports_strengths.get(s, 3) for s in ("swim", "bike", "run")]
    mean = sum(scores) / len(scores)
    if mean < 2.5:
        return "beginner"
    if mean < 3.75:
        return "intermediate"
    return "advanced"


def cap_volume(hours: float | None) -> int:
    """Jours d'entrainement max selon le volume hebdo cible."""
    h = hours or 0
    if h < 5:
        return 4
    if h < 7:
        return 5
    return 6


def cap_niveau(level: Level) -> int:
    """Plafond de jours d'entrainement selon le niveau."""
    return {"beginner": 4, "intermediate": 5, "advanced": 6}[level]


def repos_min(level: Level, phase: str) -> int:
    """Plancher de jours OFF complet. Toujours >= 1."""
    level_floor = 2 if level == "beginner" else 1
    phase_floor = 2 if phase in ("taper", "deload") else 1
    return max(level_floor, phase_floor)


def training_days_count(
    *, n_available: int, hours: float | None, level: Level, phase: str
) -> int:
    """Nombre effectif de jours d'entrainement (>= 0, garantit le plancher repos)."""
    return max(
        0,
        min(
            n_available,
            cap_volume(hours),
            cap_niveau(level),
            7 - repos_min(level, phase),
        ),
    )
