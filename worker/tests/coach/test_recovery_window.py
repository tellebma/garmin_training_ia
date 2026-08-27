"""Tests de la fenêtre de récupération post-course (E27.1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from garmin_sync.coach.recovery_window import (
    RECOVERY_SESSION_TYPES,
    post_race_recovery,
    recovery_days,
)

RACE_DAY = date(2026, 8, 23)


@pytest.mark.parametrize(
    ("elapsed_s", "expected_days"),
    [
        (70 * 60, 3),  # sprint bouclé en 1 h 10
        (89 * 60, 3),  # juste sous la bascule
        (90 * 60, 7),  # pile à la bascule : le barème supérieur s'applique
        (3 * 3600, 7),  # olympique
        (4 * 3600, 7),  # dernière seconde du palier
        (4 * 3600 + 1, 14),  # half
        (12 * 3600, 14),  # ironman
    ],
)
def test_recovery_scales_with_the_actual_duration(elapsed_s: int, expected_days: int):
    assert recovery_days(elapsed_s) == expected_days


def test_a_long_olympic_recovers_like_a_long_race_not_like_its_label():
    """Le temps passé à l'effort décide, pas l'étiquette de l'épreuve."""
    assert recovery_days(5 * 3600, "olympique") == 14
    assert recovery_days(70 * 60, "half_ironman") == 3


@pytest.mark.parametrize(
    ("distance", "expected_days"),
    [("sprint", 3), ("olympique", 7), ("half_ironman", 14), ("ironman", 14)],
)
def test_without_a_duration_the_declared_format_takes_over(distance: str, expected_days: int):
    assert recovery_days(None, distance) == expected_days


@pytest.mark.parametrize("elapsed", [None, 0, -1])
def test_unusable_duration_never_means_no_recovery(elapsed: float | None):
    """Ne rien prévoir serait le seul choix franchement mauvais."""
    assert recovery_days(elapsed, "autre") == 7


def test_window_runs_from_the_day_after_the_race():
    window = post_race_recovery(race_date=RACE_DAY, elapsed_s=3 * 3600, today=RACE_DAY)
    assert window is not None
    assert not window.covers(RACE_DAY)
    assert window.covers(RACE_DAY + timedelta(days=1))
    assert window.covers(RACE_DAY + timedelta(days=7))
    assert not window.covers(RACE_DAY + timedelta(days=8))


def test_load_is_halved_then_eased_back():
    window = post_race_recovery(race_date=RACE_DAY, elapsed_s=6 * 3600, today=RACE_DAY)
    assert window is not None
    assert window.load_multiplier(RACE_DAY + timedelta(days=2)) == 0.5
    assert window.load_multiplier(RACE_DAY + timedelta(days=7)) == 0.5
    assert window.load_multiplier(RACE_DAY + timedelta(days=8)) == 0.75
    assert window.load_multiplier(RACE_DAY + timedelta(days=30)) == 1.0


def test_no_window_when_there_is_nothing_to_impose():
    # Aucune course connue.
    assert post_race_recovery(race_date=None, elapsed_s=3600, today=RACE_DAY) is None
    # Course encore à venir : la préparation continue, ce n'est pas de la récup.
    assert (
        post_race_recovery(race_date=RACE_DAY + timedelta(days=3), elapsed_s=3600, today=RACE_DAY)
        is None
    )
    # Fenêtre terminée.
    assert (
        post_race_recovery(
            race_date=RACE_DAY, elapsed_s=3 * 3600, today=RACE_DAY + timedelta(days=8)
        )
        is None
    )


def test_a_week_is_in_recovery_as_soon_as_one_of_its_days_is():
    """Bug attrapé en test : ne regarder que le lundi ratait le cas le plus fréquent.

    Course courue un lundi (ou en fin de semaine) : la récupération commence le
    lendemain, donc la semaine EN COURS est une semaine de récupération. La tester
    sur son seul premier jour la déclarait normale — et l'athlète recevait une
    séance longue au lendemain de son épreuve.
    """
    monday = date(2026, 8, 24)
    window = post_race_recovery(race_date=monday, elapsed_s=3 * 3600, today=monday)
    assert window is not None
    assert not window.covers(monday)
    assert window.covers_week(monday)
    assert window.week_load_multiplier(monday) == 0.5


def test_a_week_straddling_the_end_of_the_window_stays_eased():
    """On préfère une semaine trop douce à une semaine trop dure après une course."""
    window = post_race_recovery(race_date=RACE_DAY, elapsed_s=3 * 3600, today=RACE_DAY)
    assert window is not None
    straddling = RACE_DAY + timedelta(days=5)  # se termine après la fin de fenêtre
    assert window.week_load_multiplier(straddling) == 0.5


def test_recovery_allows_no_quality_and_no_long_session():
    assert RECOVERY_SESSION_TYPES == ["recovery", "endurance"]
    for forbidden in ("threshold", "pma", "sprint", "long"):
        assert forbidden not in RECOVERY_SESSION_TYPES
