"""Dosage de l'intensité par niveau (#165) : on module, on n'interdit pas."""

from __future__ import annotations

import pytest

from garmin_sync.coach.intensity_dose import (
    STRIDES,
    describe_dose,
    dose_for,
    hard_types_for_level,
)


def test_every_level_has_access_to_at_least_one_quality_type() -> None:
    """Régression #165 : niveau 1 et 2 n'avaient AUCUN type dur accessible."""
    for level in range(1, 6):
        assert hard_types_for_level(level), f"niveau {level} sans aucune séance de qualité"


def test_level_1_quality_is_strides_only() -> None:
    assert hard_types_for_level(1) == {STRIDES}


def test_threshold_opens_at_level_2_pma_stays_advanced() -> None:
    assert "threshold" in hard_types_for_level(2)
    assert "pma" not in hard_types_for_level(2)
    assert "pma" not in hard_types_for_level(3)
    assert "pma" in hard_types_for_level(4)


def test_sprint_opens_at_level_3() -> None:
    assert "sprint" not in hard_types_for_level(2)
    assert "sprint" in hard_types_for_level(3)


def test_out_of_range_levels_are_clamped() -> None:
    assert hard_types_for_level(0) == hard_types_for_level(1)
    assert hard_types_for_level(9) == hard_types_for_level(5)


def test_strides_dose_at_level_1_is_short_hill_reps() -> None:
    """Le coureur niveau 1 fait des côtes courtes 6x1', pas 3x10' de seuil."""
    dose = dose_for(STRIDES, 1)
    assert dose is not None
    assert dose.reps_low == 6
    assert dose.work_s == 60
    assert dose.recovery_ratio >= 1.0  # récupération complète


def test_threshold_interval_length_grows_with_level() -> None:
    lengths = [dose_for("threshold", level) for level in (2, 3, 4, 5)]
    assert all(d is not None for d in lengths)
    work = [d.work_s for d in lengths if d is not None]
    assert work == sorted(work)
    assert work[0] < work[-1], "le dosage seuil doit s'allonger avec le niveau"
    # Le débutant confirmé ne reçoit jamais un 3x10'.
    assert work[0] <= 5 * 60


def test_dose_is_none_below_the_minimum_level_of_a_type() -> None:
    assert dose_for("threshold", 1) is None
    assert dose_for("pma", 3) is None


def test_dose_saturates_above_the_highest_defined_level() -> None:
    assert dose_for("pma", 9) == dose_for("pma", 5)


def test_dose_is_none_for_a_non_quality_type() -> None:
    assert dose_for("endurance", 3) is None


@pytest.mark.parametrize("session_type", ["strides", "threshold", "sprint", "pma"])
def test_describe_dose_is_a_french_prescription(session_type: str) -> None:
    text = describe_dose(session_type=session_type, level=5)
    assert text is not None
    assert "Dosage" in text
    assert "répétition" in text
    # Une prescription chiffrée, pas une consigne vague.
    assert any(char.isdigit() for char in text)


def test_describe_dose_returns_none_when_no_dose_applies() -> None:
    assert describe_dose(session_type="endurance", level=3) is None
    assert describe_dose(session_type="threshold", level=1) is None


def test_describe_dose_mentions_the_level_and_the_zone() -> None:
    text = describe_dose(session_type=STRIDES, level=1)
    assert text is not None
    assert "niveau 1" in text
    assert "Z4" in text or "Z5" in text
