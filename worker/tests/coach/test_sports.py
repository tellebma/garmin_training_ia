"""Test sport -> discipline mapping."""

from __future__ import annotations

from garmin_sync.coach.sports import DISCIPLINE_SPORTS, normalize_discipline


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
