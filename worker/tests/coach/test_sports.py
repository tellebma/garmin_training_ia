"""Test sport -> discipline mapping."""

from __future__ import annotations

from garmin_sync.coach.sports import (
    DISCIPLINE_SPORTS,
    NON_DISCIPLINE_LOAD_FACTOR,
    load_factor,
    normalize_discipline,
)


def test_load_factor_full_for_core_disciplines() -> None:
    assert load_factor("swim") == 1.0
    assert load_factor("bike") == 1.0
    assert load_factor("trail_running") == 1.0


def test_load_factor_reduced_for_non_discipline_sports() -> None:
    """#133 (option b): hiking/strength count at a reduced coefficient, not full."""
    assert 0.0 < NON_DISCIPLINE_LOAD_FACTOR < 1.0
    assert load_factor("hiking") == NON_DISCIPLINE_LOAD_FACTOR
    assert load_factor("strength_training") == NON_DISCIPLINE_LOAD_FACTOR
    assert load_factor("") == NON_DISCIPLINE_LOAD_FACTOR


def test_normalize_known_variants() -> None:
    assert normalize_discipline("lap_swimming") == "swim"
    assert normalize_discipline("indoor_cycling") == "bike"
    assert normalize_discipline("trail_running") == "run"
    assert normalize_discipline("run") == "run"


def test_normalize_unknown_sport_returns_none() -> None:
    assert normalize_discipline("yoga") is None
    assert normalize_discipline("") is None


def test_mapping_exposes_three_core_disciplines() -> None:
    assert {"swim", "bike", "run"} <= set(DISCIPLINE_SPORTS)
