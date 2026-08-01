"""Disponibilite != entrainement.

``available_days`` est un masque de fenetres possibles. On choisit un sous-ensemble
de jours d'entrainement plafonne par le volume, le niveau et un plancher de repos.
"""

from __future__ import annotations

Level = str  # "beginner" | "intermediate" | "advanced"


def athlete_level(sports_strengths: dict[str, int]) -> Level:
    """Niveau global derive de la moyenne des DEUX meilleures disciplines (#129).

    La moyenne des trois classait « beginner » un athlete niveau 4 en velo a
    cause d'un point faible isole (run 1) : plafond a 4 jours et 30 % du budget
    horaire declare inutilise. La capacite d'entrainement est portee par les
    points forts ; les protections specifiques (run cap) restent PAR discipline
    via ``level_label_for_score``.
    """
    scores = sorted((sports_strengths.get(s, 3) for s in ("swim", "bike", "run")), reverse=True)
    mean = sum(scores[:2]) / 2
    if mean < 2.5:
        return "beginner"
    if mean < 3.75:
        return "intermediate"
    return "advanced"


def level_label_for_score(score: int) -> Level:
    """Niveau d'UNE discipline isolee (note 1-5) — coherent avec athlete_level."""
    if score <= 2:
        return "beginner"
    if score == 3:
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


# Nombre minimal de séances observées sur la fenêtre pour considérer les
# habitudes de l'athlète comme un signal fiable (sinon étalement mécanique).
_MIN_OBSERVED_SESSIONS = 6


def select_training_days_observed(
    *,
    available_idx: set[int],
    count: int,
    weekday_counts: dict[int, int] | None,
) -> set[int]:
    """Choisit les jours d'entraînement en suivant les habitudes OBSERVÉES (#127).

    Prod : la grille mécanique lun/mer/ven/sam était reproposée chaque semaine
    alors que l'athlète posait ses grosses sorties en fin de semaine -> zéro
    correspondance prévu/réalisé sur 20 jours, et un malus d'observance en
    prime. Si le signal est suffisant (>= ``_MIN_OBSERVED_SESSIONS`` séances
    sur la fenêtre, parmi les jours disponibles), on retient les jours les plus
    utilisés ; sinon retour à l'étalement mécanique (``select_training_days``).
    """
    counts = weekday_counts or {}
    observed_total = sum(counts.get(d, 0) for d in available_idx)
    if observed_total < _MIN_OBSERVED_SESSIONS:
        return select_training_days(available_idx=available_idx, count=count)
    days = sorted(available_idx)
    if count <= 0:
        return set()
    if count >= len(days):
        return set(days)
    ranked = sorted(days, key=lambda d: (-counts.get(d, 0), d))
    return set(ranked[:count])


def long_session_day(
    training_idx: set[int], weekday_durations: dict[int, float] | None = None
) -> int | None:
    """Jour de la séance longue, dérivé des jours réellement retenus (#122/#127).

    Priorité au jour où l'athlète cumule DÉJÀ le plus de temps d'entraînement
    (``weekday_durations``) : c'est là que la grosse sortie a une chance d'être
    faite. À défaut de signal, le dernier jour d'entraînement de la semaine
    (samedi/dimanche en pratique) — l'ancien dimanche codé en dur n'était
    jamais sélectionné, donc aucune séance longue n'était jamais émise.
    """
    if not training_idx:
        return None
    if weekday_durations:
        best = max(sorted(training_idx), key=lambda d: weekday_durations.get(d, 0.0))
        if weekday_durations.get(best, 0.0) > 0:
            return best
    return max(training_idx)


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
