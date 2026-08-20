"""#165 : un niveau déclaré <= 2 n'interdit plus définitivement l'intensité.

Avant : ``_HARD_TYPES_BY_LEVEL[1] = set()`` — aucune séance de qualité, dans
aucune phase, sur toute la durée du plan. Et la phase base n'exposait aucun type
dur pour PERSONNE : la moitié d'un plan de 16 semaines était mécaniquement sans
intensité.
"""

from __future__ import annotations

from typing import Any

from garmin_sync.coach.planner import _QUALITY_SESSION_TYPES, pick_session_types_for_phase

from .conftest import OwnerWeek


def _quality(sessions: list[dict[str, Any]], sport: str | None = None) -> list[dict[str, Any]]:
    return [
        s
        for s in sessions
        if s["session_type"] in _QUALITY_SESSION_TYPES and (sport is None or s["sport"] == sport)
    ]


def test_level_1_gets_a_quality_type_in_build() -> None:
    types = pick_session_types_for_phase("build", max_level=1)
    assert set(types) & _QUALITY_SESSION_TYPES, "un niveau 1 n'a accès à aucune qualité"


def test_level_2_gets_threshold_in_build() -> None:
    types = pick_session_types_for_phase("build", max_level=2)
    assert "threshold" in types


def test_strides_available_but_threshold_not_at_level_1() -> None:
    """Le dosage remplace l'interdiction : côtes courtes 6x1', pas 3x10' de seuil."""
    types = pick_session_types_for_phase("build", max_level=1)
    assert "strides" in types
    assert "threshold" not in types


def test_base_phase_exposes_a_light_quality_type_at_every_level() -> None:
    for level in range(1, 6):
        types = pick_session_types_for_phase("base", max_level=level)
        assert set(types) & _QUALITY_SESSION_TYPES, f"base niveau {level} sans qualité"
        assert "strides" in types


def test_taper_keeps_a_light_quality_type_for_low_levels() -> None:
    types = pick_session_types_for_phase("taper", max_level=1)
    assert "strides" in types


def test_peak_keeps_a_light_quality_type_for_low_levels() -> None:
    types = pick_session_types_for_phase("peak", max_level=2)
    assert "strides" in types
    assert "pma" not in types


def test_base_week_of_a_beginner_contains_intensity(owner_week: OwnerWeek) -> None:
    assert _quality(owner_week("base")), "semaine base sans la moindre séance de qualité"
