"""Tests des cycles d'entraînement sans objectif (E27)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from garmin_sync.coach.cycles import (
    CYCLE_WEEKS,
    MAX_MULTIPLIER,
    compute_cycle_phases,
    cycle_load_multipliers,
    cycle_week,
    is_cycle_mode,
    is_deload_week,
)


def test_cycle_week_advances_one_step_per_week_and_wraps():
    since = date(2026, 8, 3)
    positions = [cycle_week(since, since + timedelta(weeks=w)) for w in range(6)]
    assert positions == [0, 1, 2, 3, 0, 1]


def test_cycle_week_is_stable_within_a_week():
    since = date(2026, 8, 3)
    assert {cycle_week(since, since + timedelta(days=d)) for d in range(7)} == {0}


def test_cycle_week_without_anchor_is_a_load_week_never_a_deload():
    """Profil jamais migré : on ne décharge pas quelqu'un qui n'a rien demandé."""
    assert cycle_week(None, date(2026, 8, 25)) == 0
    assert not is_deload_week("maintain", cycle_week(None, date(2026, 8, 25)))


def test_cycle_week_tolerates_an_anchor_in_the_future():
    since = date(2026, 9, 30)
    assert cycle_week(since, date(2026, 8, 25)) == 0


@pytest.mark.parametrize("mode", ["maintain", "improve"])
def test_deload_is_the_fourth_week_of_the_cycle(mode: str):
    flags = [is_deload_week(mode, position) for position in range(CYCLE_WEEKS)]
    assert flags == [False, False, False, True]


def test_race_mode_has_no_cycle():
    assert not is_cycle_mode("race")
    assert not is_deload_week("race", 3)
    with pytest.raises(ValueError, match="mode sans cycle"):
        compute_cycle_phases(4, "race", start_cycle_week=0)
    with pytest.raises(ValueError, match="mode sans cycle"):
        cycle_load_multipliers("race", start_cycle_week=0, weeks=4)


def test_maintain_stays_on_base_and_deloads_once_per_cycle():
    phases = compute_cycle_phases(4, "maintain", start_cycle_week=0)
    assert [phase for _, phase in phases] == ["base", "base", "base", "base"]
    assert cycle_load_multipliers("maintain", start_cycle_week=0, weeks=4) == [
        1.08,
        1.08,
        1.08,
        0.76,
    ]


def test_improve_alternates_build_weeks_without_peak_or_taper():
    phases = compute_cycle_phases(4, "improve", start_cycle_week=0)
    labels = [phase for _, phase in phases]
    assert labels == ["base", "build", "build", "base"]
    assert "peak" not in labels
    assert "taper" not in labels


def test_horizon_starts_where_the_calendar_says_not_at_zero():
    """Le deload ne recule pas : régénérer en semaine 2 place la décharge à l'offset 1."""
    multipliers = cycle_load_multipliers("improve", start_cycle_week=2, weeks=4)
    assert multipliers == [1.12, 0.79, 1.12, 1.12]
    phases = compute_cycle_phases(4, "improve", start_cycle_week=2)
    assert [phase for _, phase in phases] == ["build", "base", "base", "build"]


def test_a_calendar_week_keeps_its_factor_across_regenerations():
    """La semaine qui était « offset 1 » devient « offset 0 » avec le même facteur.

    C'est la propriété qui rend l'horizon roulant honnête : ce que l'athlète a vu
    annoncé la semaine dernière est ce qu'il reçoit cette semaine.
    """
    for mode in ("maintain", "improve"):
        this_week = cycle_load_multipliers(mode, start_cycle_week=1, weeks=4)
        next_week = cycle_load_multipliers(mode, start_cycle_week=2, weeks=4)
        assert this_week[1:] == next_week[:-1]


@pytest.mark.parametrize("mode", ["maintain", "improve"])
@pytest.mark.parametrize("start", range(CYCLE_WEEKS))
def test_no_multiplier_ever_exceeds_the_documented_ceiling(mode: str, start: int):
    """Garde-fou anti-emballement : aucune semaine ne peut demander plus de +10 %."""
    multipliers = cycle_load_multipliers(mode, start_cycle_week=start, weeks=12)
    assert max(multipliers) <= MAX_MULTIPLIER == 1.12


@pytest.mark.parametrize("mode", ["maintain", "improve"])
def test_multipliers_have_no_memory_across_cycles(mode: str):
    """Le piège du module : trois cycles d'affilée répètent les MÊMES facteurs.

    Si un jour quelqu'un compose la progression ici (comme le fait
    ``compute_week_load_multipliers`` sur un plan borné par une course), ce test
    tombe — et c'est exactement ce qu'on veut : sur un plan sans fin, la rampe
    s'appliquerait à une CTL déjà montée, deux fois la même progression.
    """
    multipliers = cycle_load_multipliers(mode, start_cycle_week=0, weeks=CYCLE_WEEKS * 3)
    first_cycle = multipliers[:CYCLE_WEEKS]
    assert multipliers == first_cycle * 3


def test_zero_or_negative_horizon_still_returns_one_week():
    """Un horizon vide produirait un plan vide, c'est-à-dire le bug qu'on répare."""
    assert len(cycle_load_multipliers("maintain", start_cycle_week=0, weeks=0)) == 1
    assert len(compute_cycle_phases(0, "maintain", start_cycle_week=0)) == 1
