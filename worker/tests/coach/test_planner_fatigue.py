"""Régression #167 : la fatigue mesurée doit dimensionner la charge.

``atl`` et ``tsb`` étaient calculés, écrits dans ``training_plans`` et jamais
relus. Prod : ``ctl 45,54 / atl 76,39 / tsb -30,85`` (surmenage non fonctionnel)
et le plan émettait quand même 367 TSS la semaine du 9 août, à 13 jours de la
course.

Corollaire : le rabais de reprise s'appliquait à ``current_offset``, qui glisse
d'une semaine à chaque régénération — la forme du plan changeait chaque lundi
(``planned_hours_reference_week`` observé à 7 h puis 3 h pour le même athlète et
la même course). Il est désormais ancré sur la DATE de début de préparation.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from garmin_sync.coach.banister import BanisterState
from garmin_sync.coach.phases import compute_phases
from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    TSB_DELOAD_THRESHOLD,
    TSB_STRONG_DELOAD_MULTIPLIER,
    TSB_STRONG_DELOAD_THRESHOLD,
    ObservedHabits,
    TrainingTarget,
    _build_all_week_sessions,
    _PlanGrid,
    tsb_load_multiplier,
)

_LEGS = [
    {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
    {"order": 2, "discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000},
    {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
]


def test_fresh_athlete_keeps_full_load() -> None:
    assert tsb_load_multiplier(5.0) == 1.0
    assert tsb_load_multiplier(-10.0) == 1.0
    assert tsb_load_multiplier(None) == 1.0


def test_functional_overreaching_forces_a_deload_week() -> None:
    assert tsb_load_multiplier(TSB_DELOAD_THRESHOLD) == DELOAD_RAMP_RATE
    assert tsb_load_multiplier(-30.0) == DELOAD_RAMP_RATE


def test_non_functional_overreaching_cuts_harder() -> None:
    assert tsb_load_multiplier(TSB_STRONG_DELOAD_THRESHOLD) == TSB_STRONG_DELOAD_MULTIPLIER
    assert tsb_load_multiplier(-45.0) == TSB_STRONG_DELOAD_MULTIPLIER
    assert TSB_STRONG_DELOAD_MULTIPLIER < DELOAD_RAMP_RATE


def _weeks(*, tsb: float, current_offset: int = 2, reprise_offset: int = 0) -> Any:
    start = date(2026, 6, 1)
    race_date = start + timedelta(weeks=10)
    phases = compute_phases(start, race_date)
    return _build_all_week_sessions(
        grid=_PlanGrid(
            phases=list(phases),
            weeks_count=len(phases),
            week_start=start,
            current_offset=current_offset,
            anchor=start,
            end_date=race_date,
            sports=["swim", "bike", "run"],
            target=TrainingTarget(race_day=race_date, sport="triathlon", legs=_LEGS),
            reprise_offset=reprise_offset,
        ),
        today_state=BanisterState(ctl=45.54, atl=45.54 - tsb, tsb=tsb),
        profile={"hours_per_week": 8},
        first_week_tss_multiplier=1.0,
        effective_strengths={"swim": 2, "bike": 4, "run": 1},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        observed=ObservedHabits(),
    )


def test_tired_athlete_gets_a_lighter_current_week() -> None:
    """TSB -30,85 (prod) : la semaine courante doit être nettement allégée."""
    fresh = _weeks(tsb=0.0)
    tired = _weeks(tsb=-30.85)
    assert tired.budget_by_offset[2] < fresh.budget_by_offset[2] * 0.8, (
        f"budget semaine courante : {tired.budget_by_offset[2]:.1f} "
        f"vs {fresh.budget_by_offset[2]:.1f} à TSB nul"
    )


def test_tsb_deload_only_touches_the_current_week() -> None:
    """La fatigue est un état d'aujourd'hui : elle ne rabote pas tout le plan."""
    fresh = _weeks(tsb=0.0)
    tired = _weeks(tsb=-40.0)
    assert tired.budget_by_offset[5] == fresh.budget_by_offset[5]


def test_tsb_deload_does_not_depress_the_following_weeks() -> None:
    """Une semaine allégée ne devient pas la nouvelle référence du ramp cap :
    sinon un seul épisode de fatigue écraserait toute la suite du plan."""
    fresh = _weeks(tsb=0.0)
    tired = _weeks(tsb=-40.0)
    assert tired.budget_by_offset[3] == fresh.budget_by_offset[3]


def test_reprise_discount_is_anchored_and_does_not_slide() -> None:
    """Le rabais de reprise suit la semaine de DÉBUT DE PRÉPA, pas la semaine
    courante : deux régénérations successives donnent le même plan."""
    start = date(2026, 6, 1)
    race_date = start + timedelta(weeks=10)
    phases = compute_phases(start, race_date)

    def _run(current_offset: int) -> dict[int, float]:
        return _build_all_week_sessions(
            grid=_PlanGrid(
                phases=list(phases),
                weeks_count=len(phases),
                week_start=start,
                current_offset=current_offset,
                anchor=start,
                end_date=race_date,
                sports=["swim", "bike", "run"],
                target=TrainingTarget(race_day=race_date, sport="triathlon", legs=_LEGS),
                reprise_offset=0,
            ),
            today_state=BanisterState(ctl=45.0, atl=45.0, tsb=0.0),
            profile={"hours_per_week": 8},
            first_week_tss_multiplier=0.85,
            effective_strengths={"swim": 3, "bike": 3, "run": 3},
            available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            observed=ObservedHabits(),
        ).budget_by_offset

    assert _run(1) == _run(4), "le budget hebdo change selon la semaine de régénération"


def test_reprise_discount_still_applies_to_the_first_prep_week() -> None:
    start = date(2026, 6, 1)
    race_date = start + timedelta(weeks=10)
    phases = compute_phases(start, race_date)

    def _run(multiplier: float) -> dict[int, float]:
        return _build_all_week_sessions(
            grid=_PlanGrid(
                phases=list(phases),
                weeks_count=len(phases),
                week_start=start,
                current_offset=3,
                anchor=start,
                end_date=race_date,
                sports=["swim", "bike", "run"],
                target=TrainingTarget(race_day=race_date, sport="triathlon", legs=_LEGS),
                reprise_offset=0,
            ),
            today_state=BanisterState(ctl=45.0, atl=45.0, tsb=0.0),
            profile={"hours_per_week": 8},
            first_week_tss_multiplier=multiplier,
            effective_strengths={"swim": 3, "bike": 3, "run": 3},
            available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            observed=ObservedHabits(),
        ).budget_by_offset

    assert _run(0.85)[0] < _run(1.0)[0]
