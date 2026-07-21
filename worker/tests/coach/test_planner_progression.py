"""Régression progression de charge : le ramp +5 %/semaine doit se COMPOSER.

Bug : base_weekly constante x 1.05 à chaque semaine -> charge plate (aucune montée
en charge), la progression reposait uniquement sur une dérive de CTL quasi nulle."""

from __future__ import annotations

from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    compute_week_load_multipliers,
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
