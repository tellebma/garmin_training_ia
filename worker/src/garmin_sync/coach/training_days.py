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


def allocate_sport_sessions(
    *,
    count: int,
    time_shares: dict[str, float],
    strengths: dict[str, int],
    run_cap_value: int | None = None,
) -> dict[str, int]:
    """Nombre de séances par sport, piloté par l'ENJEU de course (#130).

    L'ancienne rotation suivait l'ordre chronologique des legs (swim, bike, run,
    swim…) : la natation, ~10 % du temps de course, recevait 50 % des séances.
    Ici la part de temps estimée par discipline pondère la répartition, croisée
    avec un léger biais point-faible (niveau 1 -> +20 %, niveau 5 -> -20 %) —
    la spécificité de l'épreuve prime, le rééquilibrage reste marginal.

    Garanties : chaque discipline de la course garde >= 1 séance quand le nombre
    de jours le permet ; sinon les plus gros enjeux sont servis d'abord.
    ``run_cap_value`` borne les jours de course (impact traumatisant), le
    surplus est reporté sur la discipline non-run la plus pondérée.
    """
    sports = [s for s in time_shares if time_shares[s] > 0] or list(time_shares)
    if count <= 0 or not sports:
        return {}
    weights = {
        s: max(0.01, time_shares[s]) * (1 + 0.10 * (3 - strengths.get(s, 3))) for s in sports
    }
    order = {s: i for i, s in enumerate(sports)}
    ranked = sorted(sports, key=lambda s: (-weights[s], order[s]))
    if count < len(sports):
        counts = dict.fromkeys(ranked[:count], 1)
        return counts

    counts = dict.fromkeys(sports, 1)
    rest = count - len(sports)
    total_w = sum(weights.values())
    quotas = {s: weights[s] / total_w * rest for s in sports}
    for s in sports:
        counts[s] += int(quotas[s])
    leftover = count - sum(counts.values())
    by_remainder = sorted(sports, key=lambda s: (-(quotas[s] - int(quotas[s])), order[s]))
    for s in by_remainder[:leftover]:
        counts[s] += 1

    if run_cap_value is not None and counts.get("run", 0) > run_cap_value:
        surplus = counts["run"] - run_cap_value
        counts["run"] = run_cap_value
        non_run = [s for s in ranked if s != "run"]
        if non_run:
            counts[non_run[0]] += surplus
    return counts


def assign_sports(
    *,
    training_idx: list[int],
    sport_counts: dict[str, int],
    long_day_idx: int | None = None,
) -> dict[int, str]:
    """Place les séances de chaque sport sur les jours d'entraînement.

    Règles : la discipline dominante (le plus de séances = le plus gros enjeu)
    prend le jour de la séance longue ; jamais deux jours "run" consécutifs ;
    on alterne au maximum (le sport le plus « en retard » passe en premier).
    """
    days = sorted(training_idx)
    remaining = {s: c for s, c in sport_counts.items() if c > 0}
    if not remaining:
        return dict.fromkeys(days, "run")

    assignment: dict[int, str] = {}
    if long_day_idx in training_idx:
        dominant = max(remaining, key=lambda s: remaining[s])
        assignment[long_day_idx] = dominant
        remaining[dominant] -= 1

    prev: str | None = None
    for day in days:
        if day in assignment:
            prev = assignment[day]
            continue
        candidates = [s for s in remaining if remaining[s] > 0]
        allowed = [s for s in candidates if not (s == "run" and prev == "run")]
        if not allowed:
            # Plus que du run après un run : on substitue le meilleur non-run
            # (surplus reporté, comme l'ancien comportement).
            non_run = [s for s in sport_counts if s != "run"]
            allowed = non_run or candidates or ["run"]
        pick = max(allowed, key=lambda s: remaining.get(s, 0))
        if remaining.get(pick, 0) > 0:
            remaining[pick] -= 1
        assignment[day] = pick
        prev = pick
    return assignment
