"""Test sport -> discipline mapping."""

from __future__ import annotations

import pytest

from garmin_sync.coach.sports import (
    BRICK_SPORTS,
    CORE_DISCIPLINES,
    DISCIPLINE_SPORTS,
    NON_DISCIPLINE_LOAD_FACTOR,
    contributing_disciplines,
    elevation_discipline,
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
    assert CORE_DISCIPLINES == ("swim", "bike", "run")


@pytest.mark.parametrize("sport", sorted(BRICK_SPORTS))
def test_brick_sports_are_a_discipline_at_full_load(sport: str) -> None:
    """#169 — an enchaînement is the most race-specific session there is.

    Falling through to NON_DISCIPLINE_LOAD_FACTOR (meant for hiking/yoga) made a
    3 h 57 multi_sport count half in CTL/ATL.
    """
    assert normalize_discipline(sport) == "brick"
    assert load_factor(sport) == 1.0


def test_brick_trains_both_bike_and_run() -> None:
    assert contributing_disciplines("multi_sport") == {"bike", "run"}
    assert contributing_disciplines("brick") == {"bike", "run"}


def test_contributing_disciplines_of_a_single_sport_is_itself() -> None:
    assert contributing_disciplines("trail_running") == {"run"}
    assert contributing_disciplines("open_water_swimming") == {"swim"}


def test_contributing_disciplines_empty_for_non_discipline_sports() -> None:
    assert contributing_disciplines("hiking") == set()
    assert contributing_disciplines("") == set()


def test_brick_elevation_is_credited_to_the_bike_leg() -> None:
    """A brick's D+ is earned almost entirely on the bike; crediting it to run
    too would double-count it and inflate the run D+ ramp."""
    assert elevation_discipline("multi_sport") == "bike"
    assert elevation_discipline("transition") == "bike"


def test_elevation_discipline_matches_normalize_for_single_sports() -> None:
    assert elevation_discipline("trail_running") == "run"
    assert elevation_discipline("indoor_cycling") == "bike"
    assert elevation_discipline("hiking") is None
