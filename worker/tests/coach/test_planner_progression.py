"""Régression progression de charge : le ramp +5 %/semaine doit se COMPOSER.

Bug : base_weekly constante x 1.05 à chaque semaine -> charge plate (aucune montée
en charge), la progression reposait uniquement sur une dérive de CTL quasi nulle."""

from __future__ import annotations

from garmin_sync.coach.planner import (
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


_ELEV_PHASES = [
    (0, "base"),
    (1, "base"),
    (2, "base"),
    (3, "build"),
    (4, "build"),
    (5, "build"),
    (6, "peak"),
    (7, "taper"),
]


def test_elevation_target_drops_in_taper() -> None:
    """Le D+ hebdo doit BAISSER en taper : on ne va pas grimper 2000 m la semaine
    avant la course (bug prod : 500 m ciblés en pleine semaine de taper)."""
    peak = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=6,
        phases=_ELEV_PHASES,
        observed_weekly_dplus={"bike": 600},
    )
    taper = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=7,
        phases=_ELEV_PHASES,
        observed_weekly_dplus={"bike": 600},
    )
    assert taper["bike"] < peak["bike"]


def test_elevation_target_is_monotonic_until_peak() -> None:
    """La cible D+ PROGRESSE vers un pic >= D+ de course en fin de build/peak,
    au lieu d'étaler le total de la course sur la préparation (bug prod :
    500 m/sem constants pour 2000 m de course, jamais atteints)."""
    targets = [
        compute_weekly_elevation_targets(
            race_dplus_by_sport={"bike": 2000},
            week_offset=w,
            phases=_ELEV_PHASES,
            observed_weekly_dplus={"bike": 800},
        )["bike"]
        for w, _ in _ELEV_PHASES[:-1]  # hors taper
    ]
    assert targets == sorted(targets), f"progression non monotone : {targets}"
    assert targets[-1] >= 1999, f"le pic ({targets[-1]}) doit couvrir le D+ de course"
    # Stable par régénération : la cible dépend du week_offset ancré, plus d'un
    # horizon restant qui rétrécit (l'explosion 166 -> 500 -> 1000 m/sem est
    # rendue impossible par construction).
    again = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=3,
        phases=_ELEV_PHASES,
        observed_weekly_dplus={"bike": 800},
    )["bike"]
    assert again == targets[3]
