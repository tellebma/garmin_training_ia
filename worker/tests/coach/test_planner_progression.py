"""Régression progression de charge : le ramp +5 %/semaine doit se COMPOSER.

Bug : base_weekly constante x 1.05 à chaque semaine -> charge plate (aucune montée
en charge), la progression reposait uniquement sur une dérive de CTL quasi nulle."""

from __future__ import annotations

from garmin_sync.coach.planner import (
    _MIN_ELEVATION_SPREAD_WEEKS,
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    compute_week_load_multipliers,
    compute_weekly_elevation_targets,
)

_PHASES = [
    (0, "base"),
    (1, "base"),
    (2, "base"),
    (3, "build"),  # 4e semaine -> deload
    (4, "build"),
    (5, "build"),
    (6, "peak"),
    (7, "taper"),
]


def test_normal_weeks_compound_upward() -> None:
    m = compute_week_load_multipliers(_PHASES)
    assert m[0] == 1.0
    # Semaines de build normales (hors deload) : strictement croissantes.
    assert m[1] == round(NORMAL_RAMP_RATE, 4)
    assert m[2] > m[1]
    assert m[4] > m[2]  # la progression reprend après le deload
    assert m[5] > m[4]
    assert m[6] > m[5]


def test_deload_week_steps_back() -> None:
    m = compute_week_load_multipliers(_PHASES)
    # offset 3 = 4e semaine -> deload : charge sous la semaine précédente.
    assert m[3] < m[2]
    assert m[3] == round(m[2] / 1.0 * DELOAD_RAMP_RATE, 4) or m[3] < m[2]


def test_taper_is_lowest_relative_to_peak() -> None:
    m = compute_week_load_multipliers(_PHASES)
    assert m[7] < m[6]


def test_progression_actually_happens_over_plan() -> None:
    """Le pic de charge en fin de build doit dépasser nettement la semaine 0."""
    m = compute_week_load_multipliers(_PHASES)
    assert max(m) > 1.10, "aucune montée en charge réelle sur le plan"


def test_elevation_target_drops_in_taper() -> None:
    """Le D+ hebdo doit BAISSER en taper : on ne va pas grimper 500 m la semaine
    avant la course (bug prod : 500 m ciblés en pleine semaine de taper)."""
    build = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000}, weeks_count=8, phase="build"
    )
    taper = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000}, weeks_count=8, phase="taper"
    )
    assert taper["bike"] < build["bike"]


def test_elevation_target_does_not_explode_as_race_approaches() -> None:
    """Bug prod : `D+ total / semaines restantes` recalculé chaque dimanche sur un
    horizon qui rétrécit -> 166 m/sem à 12 semaines, 500 m à 4, 1000 m à 2.
    Un plancher de dénominateur borne la cible."""
    far = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000}, weeks_count=8, phase="build"
    )
    near = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000}, weeks_count=2, phase="build"
    )
    assert near["bike"] == 2000 // 4, "la cible doit être bornée, pas 1000 m/sem"
    # Sans plancher, 2 semaines restantes donneraient 1000 m/sem : le cap divise ça par 2.
    assert near["bike"] == 2000 // _MIN_ELEVATION_SPREAD_WEEKS
    assert far["bike"] == 2000 // 8
