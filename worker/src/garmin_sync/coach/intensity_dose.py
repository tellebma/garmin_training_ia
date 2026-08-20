"""Dosage de l'intensité par niveau : on module, on n'interdit pas (#165).

Avant : ``_HARD_TYPES_BY_LEVEL[1] = set()`` — un athlète noté 1 ou 2 dans une
discipline ne pouvait recevoir AUCUNE séance de qualité, dans aucune phase, sur
toute la durée du plan. Combiné au biais point faible (+25 % de volume sur la
discipline la plus faible), le maillon faible recevait « beaucoup de kilomètres
lents » : le protocole le moins efficace qui soit.

Ici, le niveau pilote le DOSAGE — nature de la répétition, durée, nombre,
récupération, zone cible — et non l'accès. Un coureur niveau 1 fait des côtes
courtes 6x1' ; un niveau 5 fait 4x10' de seuil. Les deux travaillent.

Ce module est la source de vérité : le planner en dérive les types accessibles
par niveau, et le prompt LLM en dérive la prescription chiffrée envoyée au
modèle (sans quoi « threshold niveau 2 » redeviendrait un 3x10' générique).
"""

from __future__ import annotations

from dataclasses import dataclass

# Type de qualité LÉGER, accessible à tous les niveaux et dans toutes les phases
# (y compris `base`) : répétitions courtes en côte ou en accélération, sous le
# seuil d'accumulation de lactate. C'est ce qui évite qu'une phase base de 8
# semaines soit une traversée du désert.
STRIDES = "strides"

_MIN_LEVEL = 1
_MAX_LEVEL = 5


@dataclass(frozen=True)
class IntensityDose:
    """Prescription chiffrée d'une séance de qualité pour un niveau donné."""

    reps_low: int
    reps_high: int
    work_s: int
    # Récupération = work_s x recovery_ratio (un débutant récupère plus longtemps
    # entre des répétitions plus courtes).
    recovery_ratio: float
    zone: str


# Nature de l'effort, par type : ce que la séance CHERCHE, en français coach.
_FOCUS_BY_TYPE: dict[str, str] = {
    STRIDES: (
        "Côtes courtes ou accélérations progressives, récupération complète en trottinant "
        "ou en roulant très facile : on développe la force et la vitesse sans accumuler "
        "de lactate — jamais de série longue ici."
    ),
    "threshold": (
        "Blocs continus à l'allure seuil, tenus régulièrement : on cherche le rythme "
        "soutenable, pas l'épuisement."
    ),
    "pma": (
        "Répétitions au plafond aérobie (VO2max), récupération égale au temps de travail : "
        "on vise la puissance maximale aérobie."
    ),
    "sprint": (
        "Répétitions très courtes à intensité maximale, récupération large et complète : "
        "on vise la force explosive et la vitesse de pointe."
    ),
}

# Dosage par (type, niveau). Un type absent d'un niveau n'est pas accessible à
# ce niveau : la progression est verrouillée par la capacité à encaisser, pas
# par une interdiction de principe.
#   - strides : 1-5  (tout le monde, dès la phase base)
#   - threshold : 2-5 (dose courte au niveau 2 : 5x3', pas 3x10')
#   - sprint : 3-5
#   - pma : 4-5
_DOSES: dict[str, dict[int, IntensityDose]] = {
    STRIDES: {
        1: IntensityDose(reps_low=6, reps_high=8, work_s=60, recovery_ratio=2.0, zone="Z4"),
        2: IntensityDose(reps_low=8, reps_high=10, work_s=60, recovery_ratio=2.0, zone="Z4"),
        3: IntensityDose(reps_low=8, reps_high=10, work_s=45, recovery_ratio=1.5, zone="Z5"),
        4: IntensityDose(reps_low=10, reps_high=12, work_s=45, recovery_ratio=1.5, zone="Z5"),
        5: IntensityDose(reps_low=10, reps_high=12, work_s=45, recovery_ratio=1.0, zone="Z5"),
    },
    "threshold": {
        2: IntensityDose(reps_low=4, reps_high=5, work_s=180, recovery_ratio=0.67, zone="Z4"),
        3: IntensityDose(reps_low=3, reps_high=4, work_s=360, recovery_ratio=0.50, zone="Z4"),
        4: IntensityDose(reps_low=3, reps_high=4, work_s=480, recovery_ratio=0.38, zone="Z4"),
        5: IntensityDose(reps_low=3, reps_high=4, work_s=600, recovery_ratio=0.30, zone="Z4"),
    },
    "sprint": {
        3: IntensityDose(reps_low=6, reps_high=8, work_s=10, recovery_ratio=9.0, zone="Z5"),
        4: IntensityDose(reps_low=8, reps_high=10, work_s=12, recovery_ratio=8.0, zone="Z5"),
        5: IntensityDose(reps_low=10, reps_high=12, work_s=15, recovery_ratio=6.0, zone="Z5"),
    },
    "pma": {
        4: IntensityDose(reps_low=6, reps_high=8, work_s=120, recovery_ratio=1.0, zone="Z5"),
        5: IntensityDose(reps_low=5, reps_high=6, work_s=180, recovery_ratio=1.0, zone="Z5"),
    },
}


def clamp_level(level: int) -> int:
    """Niveau borné à l'échelle 1-5 (un profil peut porter n'importe quel entier)."""
    return max(_MIN_LEVEL, min(_MAX_LEVEL, level))


def hard_types_for_level(level: int) -> set[str]:
    """Types de qualité accessibles à ce niveau — jamais vide (#165).

    Le plancher est ``strides`` : même un grand débutant a droit à une forme
    d'intensité, dosée pour lui.
    """
    lvl = clamp_level(level)
    return {stype for stype, doses in _DOSES.items() if any(k <= lvl for k in doses)}


def dose_for(session_type: str, level: int) -> IntensityDose | None:
    """Dosage prescrit, ou None si ce type n'est pas accessible à ce niveau."""
    doses = _DOSES.get(session_type)
    if not doses:
        return None
    lvl = clamp_level(level)
    eligible = [k for k in doses if k <= lvl]
    if not eligible:
        return None
    return doses[max(eligible)]


def _fmt_duration(seconds: int) -> str:
    """10 -> « 10 s » ; 60 -> « 1'00 » ; 600 -> « 10'00 » (notation coach)."""
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60}'{seconds % 60:02d}"


def describe_dose(*, session_type: str, level: int) -> str | None:
    """Prescription chiffrée pour le prompt LLM, ou None si aucun dosage ne s'applique.

    C'est la contrepartie indispensable de l'ouverture de l'intensité aux
    niveaux faibles : sans cette ligne, « threshold » redevient un 3x10'
    générique quel que soit l'athlète.
    """
    dose = dose_for(session_type, level)
    if dose is None:
        return None
    recovery_s = round(dose.work_s * dose.recovery_ratio)
    focus = _FOCUS_BY_TYPE.get(session_type, "")
    return (
        f"Dosage imposé (niveau {clamp_level(level)}/5 dans cette discipline) : "
        f"{dose.reps_low} à {dose.reps_high} répétitions de {_fmt_duration(dose.work_s)} "
        f"à {dose.zone}, récupération {_fmt_duration(recovery_s)} entre les répétitions. "
        f"{focus}"
    )
