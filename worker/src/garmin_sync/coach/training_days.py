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


def training_days_count(*, n_available: int, hours: float | None, level: Level, phase: str) -> int:
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


def run_cap(level: Level) -> int:
    """Jours course max/semaine (impact traumatisant)."""
    return {"beginner": 2, "intermediate": 3, "advanced": 4}[level]


def select_training_days(*, available_idx: set[int], count: int) -> set[int]:
    """Choisit `count` jours parmi les dispo en les espaçant le plus possible."""
    days = sorted(available_idx)
    if count <= 0:
        return set()
    if count >= len(days):
        return set(days)
    step = len(days) / count
    picked = {days[min(len(days) - 1, round(i * step))] for i in range(count)}
    i = 0
    while len(picked) < count and i < len(days):
        picked.add(days[i])
        i += 1
    return set(sorted(picked)[:count])


def long_session_day(training_idx: set[int]) -> int | None:
    """Jour de la séance longue : le DERNIER jour d'entraînement de la semaine.

    Dérivé des jours réellement retenus (et non d'un index en dur) : le dimanche
    codé en dur n'était jamais sélectionné par ``select_training_days``, donc
    aucune séance longue n'était jamais émise (#122). Le dernier jour (samedi ou
    dimanche en pratique) laisse la semaine récupérer après la grosse sortie.
    """
    return max(training_idx) if training_idx else None


def assign_sports(
    *, training_idx: list[int], sports_in_race: list[str], level: Level
) -> dict[int, str]:
    """Assigne un sport à chaque jour d'entraînement.

    Règles : jamais deux jours "run" consécutifs, cap course par niveau, surplus
    reporté sur les autres sports (faible impact).
    """
    if not sports_in_race:
        return dict.fromkeys(sorted(training_idx), "run")
    ordered = sorted(training_idx)
    non_run = [s for s in sports_in_race if s != "run"] or ["rest"]
    cap = run_cap(level) if "run" in sports_in_race else 0
    assignment: dict[int, str] = {}
    run_used = 0
    prev: str | None = None
    for rotation, day in enumerate(ordered):
        candidate = sports_in_race[rotation % len(sports_in_race)]
        blocked_run = candidate == "run" and (prev == "run" or run_used >= cap)
        if blocked_run:
            candidate = non_run[(rotation + 1) % len(non_run)]
        if candidate == "run":
            run_used += 1
        assignment[day] = candidate
        prev = candidate
    return assignment
