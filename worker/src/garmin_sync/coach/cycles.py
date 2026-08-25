"""Cycles d'entraînement sans objectif daté (E27).

Sans course, il n'y a pas de compte à rebours : ni pic, ni affûtage, ni dernière
semaine. Le plan devient un **horizon roulant** de quelques semaines, régénéré chaque
semaine, structuré en cycles de 4 semaines (3 de charge + 1 de décharge).

Deux règles portent tout le reste de ce module, et elles ne sont pas décoratives :

1. **Les multiplicateurs sont intra-cycle, sans mémoire.** Ils dépendent uniquement de
   la position dans le cycle, jamais d'une progression cumulée depuis le début du mode.
   La progression réelle d'un cycle à l'autre est portée par la CTL MESURÉE qui monte
   (``compute_base_weekly_tss`` vaut ``ctl * 7``) : composer en plus une rampe sur une
   CTL déjà montée appliquerait deux fois la même progression, et la charge demandée
   exploserait en quelques semaines. C'est le seul vrai piège de ce moteur.

2. **La décharge est ancrée sur un calendrier absolu**, pas sur la position dans
   l'horizon. L'horizon repart à zéro à chaque régénération : un deload placé « en 4e
   semaine de l'horizon » reculerait indéfiniment et n'arriverait jamais. L'ancre est
   ``athlete_profiles.training_mode_since``, qui ne bouge qu'au changement de mode.

Le maintien, lui, ne demande aucun calcul nouveau : à l'équilibre du modèle exponentiel,
la CTL est la moyenne glissante du TSS quotidien — maintenir sa CTL, c'est produire
exactement ``7 * CTL`` de TSS par semaine, soit ``base_weekly`` avec un multiplicateur
de 1.0.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from garmin_sync.coach.phases import Phase

TrainingMode = Literal["race", "maintain", "improve"]

CYCLE_WEEKS = 4
"""Longueur d'un cycle : 3 semaines de charge + 1 de décharge."""

DEFAULT_HORIZON_WEEKS = 4
"""Assez pour voir venir un bloc et sa décharge, assez court pour ne pas mentir."""

# Facteurs RELATIFS à la CTL du moment, répétés à l'identique à chaque cycle.
# Aucun ne dépasse 1.10 : la garantie anti-emballement est dans la donnée, pas dans
# un commentaire.
_MULTIPLIERS: dict[str, tuple[float, ...]] = {
    "maintain": (1.0, 1.0, 1.0, 0.70),
    "improve": (1.0, 1.05, 1.10, 0.75),
}

_CYCLE_PHASES: dict[str, tuple[Phase, ...]] = {
    # Maintien : que de l'entretien. `base` donne endurance / long / recovery.
    "maintain": ("base", "base", "base", "base"),
    # Progression : deux semaines de qualité par cycle, encadrées par une semaine
    # d'assise et une de décharge. Ni `peak` ni `taper` : ce sont des phases qui
    # affûtent VERS une date, elles n'ont aucun sens sans épreuve.
    "improve": ("base", "build", "build", "base"),
}

MAX_MULTIPLIER = max(m for values in _MULTIPLIERS.values() for m in values)


def is_cycle_mode(mode: str | None) -> bool:
    """Ce mode se planifie-t-il en cycles (par opposition à une prépa course) ?"""
    return mode in _MULTIPLIERS


def cycle_week(mode_since: date | None, today: date) -> int:
    """Position 0..3 dans le cycle, ancrée sur un calendrier absolu.

    ``mode_since`` absente (profil jamais migré) : on retombe sur 0, c'est-à-dire une
    semaine de charge — jamais une décharge non demandée.

    Une ancre dans le futur (horloge de travers, saisie manuelle) est bornée
    explicitement : la division entière de Python arrondit vers le bas, et on ne veut
    dépendre d'aucune subtilité d'arrondi sur un nombre négatif.
    """
    if mode_since is None:
        return 0
    weeks = (today - mode_since).days // 7
    return max(0, weeks) % CYCLE_WEEKS


def is_deload_week(mode: str, cycle_position: int) -> bool:
    """La 4e semaine de chaque cycle est la décharge."""
    return is_cycle_mode(mode) and cycle_position % CYCLE_WEEKS == CYCLE_WEEKS - 1


def compute_cycle_phases(
    weeks: int, mode: str, *, start_cycle_week: int
) -> list[tuple[int, Phase]]:
    """``[(offset, phase), ...]`` sur ``weeks`` semaines, à partir du cycle en cours.

    Même forme de retour que ``compute_phases`` (prépa course) : tout l'aval du planner
    — sélection des types de séance, budgets, cibles de D+ — reste inchangé.
    """
    phases = _CYCLE_PHASES.get(mode)
    if phases is None:
        raise ValueError(f"mode sans cycle : {mode!r}")
    return [
        (offset, phases[(start_cycle_week + offset) % CYCLE_WEEKS])
        for offset in range(max(1, weeks))
    ]


def cycle_load_multipliers(mode: str, *, start_cycle_week: int, weeks: int) -> list[float]:
    """Multiplicateur de charge par semaine d'horizon, relatif à la CTL mesurée.

    Volontairement SANS mémoire d'une semaine à l'autre : cf. règle 1 du module.
    """
    multipliers = _MULTIPLIERS.get(mode)
    if multipliers is None:
        raise ValueError(f"mode sans cycle : {mode!r}")
    return [
        multipliers[(start_cycle_week + offset) % CYCLE_WEEKS] for offset in range(max(1, weeks))
    ]
