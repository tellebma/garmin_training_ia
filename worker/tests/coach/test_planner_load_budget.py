"""Régression #164 : la charge ÉMISE doit rester celle du budget calculé.

Bug prod (semaine du 2026-08-09, plan ``bfe5ce13``) : le clamp de durée servant
aussi de PLANCHER, le vélo budgété à 80,8 TSS sortait à 202,5 (x2,5) et la
semaine entière à 367 TSS pour 284,5 budgétés (+29 %) — les trois ramp caps par
sport franchis simultanément (run +56 %, bike +90 %, swim +17 %).

Le test de propriété en fin de fichier est le garde-fou durable : sur un
échantillon de profils, de courses et d'horizons, le TSS émis reste dans le
budget à +/- 10 % et la progression par sport respecte ``WEEKLY_RAMP_CAP``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from garmin_sync.coach.banister import BanisterState
from garmin_sync.coach.duration_bounds import duration_bounds_s
from garmin_sync.coach.phases import compute_phases
from garmin_sync.coach.planner import (
    LOAD_BUDGET_TOLERANCE,
    WEEKLY_RAMP_CAP,
    ObservedHabits,
    TrainingTarget,
    WeekSlot,
    _PlanGrid,
    _build_all_week_sessions,
    _build_week_sessions,
    _tss_per_hour,
    compute_elevation_per_sport,
    estimate_race_time_shares,
    race_has_bike_run_transition,
)

_NON_TRAINING = {"rest", "race"}


def _training(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in sessions if s["session_type"] not in _NON_TRAINING]


def _emitted_by_sport(sessions: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in _training(sessions):
        out[s["sport"]] = round(out.get(s["sport"], 0.0) + float(s["target_tss"]), 2)
    return out


def _prod_week(tss_by_sport: dict[str, float]) -> list[dict[str, Any]]:
    """La semaine de prod du 2026-08-09, rejouée avec ses budgets réels."""
    return _build_week_sessions(
        slot=WeekSlot(
            offset=1,
            phase="build",
            start=date(2026, 8, 9),
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 2, "bike": 4, "run": 1},
        tss_by_sport=tss_by_sport,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        # Course de l'athlète : 47 km / 2000 m D+ à vélo, soit ~66 % du temps estimé.
        target=TrainingTarget(
            race_day=date(2026, 8, 22),
            sport="triathlon",
            time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        ),
    )


def test_prod_week_total_stays_within_budget() -> None:
    """284,5 TSS budgétés -> plus jamais 367 émis."""
    budgets = {"swim": 97.6, "bike": 80.8, "run": 106.1}
    sessions = _prod_week(budgets)
    emitted = sum(float(s["target_tss"]) for s in _training(sessions))
    budget_total = sum(budgets.values())
    assert emitted <= budget_total * (1 + LOAD_BUDGET_TOLERANCE), (
        f"{emitted:.1f} TSS émis pour {budget_total:.1f} budgétés"
    )


def test_prod_week_bike_no_longer_emits_double_its_budget() -> None:
    """Le plancher de `bike long build` (150 min = 112,5 TSS) ne doit plus imposer
    une sortie que le budget ne paye pas.

    Le vélo garde plus que sa part stricte — la natation, saturée par ses plafonds
    de durée, lui rend son reliquat — mais il ne double plus son budget, et la
    semaine entière retombe dessus (cf. le test précédent)."""
    sessions = _prod_week({"swim": 97.6, "bike": 80.8, "run": 106.1})
    bike = _emitted_by_sport(sessions).get("bike", 0.0)
    assert bike <= 80.8 * 1.6, f"vélo émis à {bike} pour 80,8 budgétés (avant : 172,5)"
    assert not [s for s in _training(sessions) if s["session_type"] == "long"], (
        "une sortie longue est encore émise alors que le budget ne la paye pas"
    )


def test_residual_budget_is_redistributed_to_unsaturated_sessions() -> None:
    """Deuxième passe : une séance figée sur sa borne rend (ou prend) son résidu
    aux autres, au lieu de laisser le total dériver."""
    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["bike"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"bike": 200.0},
        available_days=["mon", "wed", "fri"],
        hours_per_week=8,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="bike"),
    )
    emitted = sum(float(s["target_tss"]) for s in _training(sessions))
    assert 200.0 * 0.9 <= emitted <= 200.0 * 1.1, f"{emitted} TSS émis pour 200 budgétés"


def test_unaffordable_session_is_downgraded_not_emitted_at_full_floor() -> None:
    """Un budget vélo qui ne paye pas une sortie longue en fait une séance plus
    modeste — il n'émet pas 112,5 TSS pour 40 budgétés."""
    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="build",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["bike"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"bike": 40.0},
        available_days=["tue", "sat"],
        hours_per_week=3,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="bike"),
    )
    training = _training(sessions)
    assert training, "une semaine ne doit jamais être vidée de toutes ses séances"
    emitted = sum(float(s["target_tss"]) for s in training)
    assert emitted <= 40.0 * (1 + LOAD_BUDGET_TOLERANCE), f"{emitted} TSS émis pour 40 budgétés"


# --- Échantillon du test de propriété -------------------------------------------------

_ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_OLYMPIC_HILLY = [
    {"order": 1, "discipline": "swim", "distance_km": 1.5, "elevation_gain_m": 0},
    {"order": 2, "discipline": "bike", "distance_km": 40, "elevation_gain_m": 900},
    {"order": 3, "discipline": "run", "distance_km": 10, "elevation_gain_m": 150},
]
_SPRINT_FLAT = [
    {"order": 1, "discipline": "swim", "distance_km": 0.75, "elevation_gain_m": 0},
    {"order": 2, "discipline": "bike", "distance_km": 20, "elevation_gain_m": 60},
    {"order": 3, "discipline": "run", "distance_km": 5, "elevation_gain_m": 20},
]
_DUATHLON = [
    {"order": 1, "discipline": "run", "distance_km": 10, "elevation_gain_m": 120},
    {"order": 2, "discipline": "bike", "distance_km": 60, "elevation_gain_m": 1200},
    {"order": 3, "discipline": "run", "distance_km": 5, "elevation_gain_m": 60},
]
_TRAIL = [{"order": 1, "discipline": "run", "distance_km": 42, "elevation_gain_m": 2200}]

# (libellé, heures déclarées, niveaux, jours dispo, CTL de départ)
_ATHLETES = [
    ("débutant 4 h", 4.0, {"swim": 1, "bike": 2, "run": 1}, ["tue", "thu", "sat"], 18.0),
    ("intermédiaire 8 h", 8.0, {"swim": 3, "bike": 3, "run": 3}, _ALL_DAYS, 42.0),
    ("avancé 12 h", 12.0, {"swim": 4, "bike": 5, "run": 4}, _ALL_DAYS, 70.0),
    ("gros volume 15 h", 15.0, {"swim": 5, "bike": 5, "run": 3}, _ALL_DAYS, 88.0),
]
_RACES = [
    ("olympique vallonné", _OLYMPIC_HILLY),
    ("sprint plat", _SPRINT_FLAT),
    ("duathlon", _DUATHLON),
    ("trail", _TRAIL),
]
_HORIZONS = [8, 14, 20]

_SAMPLE = [
    pytest.param(athlete, race, weeks, id=f"{athlete[0]}-{race[0]}-{weeks}sem")
    for athlete in _ATHLETES
    for race in _RACES
    for weeks in _HORIZONS
]


def _ceiling_tss(session: dict[str, Any]) -> float:
    """TSS maximal qu'une séance peut porter sans sortir de ses bornes de durée."""
    bounds = duration_bounds_s(session["sport"], session["session_type"], session["phase"])
    high = bounds[1] if bounds else 6 * 3600
    return high / 3600 * _tss_per_hour(session["sport"], session["session_type"])


def _plan_for(
    athlete: tuple[str, float, dict[str, int], list[str], float],
    legs: list[dict[str, Any]],
    weeks: int,
) -> tuple[Any, list[tuple[int, str]]]:
    _, hours, strengths, days, ctl = athlete
    start = date(2026, 1, 5)
    race_date = start + timedelta(weeks=weeks)
    phases = compute_phases(start, race_date)
    sports_in_race = list(dict.fromkeys(leg["discipline"] for leg in legs))
    plan = _build_all_week_sessions(
        grid=_PlanGrid(
            phases=list(phases),
            weeks_count=len(phases),
            week_start=start,
            current_offset=0,
            anchor=start,
            end_date=race_date,
            sports=sports_in_race,
            target=TrainingTarget(
                race_day=race_date,
                sport="triathlon" if len(sports_in_race) == 3 else sports_in_race[0],
                time_shares=estimate_race_time_shares(legs),
                dplus_by_sport=compute_elevation_per_sport(legs),
                has_bike_run_transition=race_has_bike_run_transition(legs),
                legs=legs,
            ),
        ),
        today_state=BanisterState(ctl=ctl, atl=ctl, tsb=0.0),
        profile={"hours_per_week": hours},
        first_week_tss_multiplier=1.0,
        effective_strengths=strengths,
        available_days=days,
        observed=ObservedHabits(),
    )
    return plan, list(phases)


def _attainable_tss(training: list[dict[str, Any]], previous: dict[str, float] | None) -> float:
    """Charge maximale que la semaine POUVAIT porter, sport par sport.

    Deux limites légitimes : les plafonds de durée des séances retenues, et le
    cap de progression hebdo mesuré sur le TSS émis la semaine de référence.
    """
    ceilings: dict[str, float] = {}
    for s in training:
        ceilings[s["sport"]] = ceilings.get(s["sport"], 0.0) + _ceiling_tss(s)
    total = 0.0
    for sport, ceiling in ceilings.items():
        prev = (previous or {}).get(sport)
        ramp = prev * WEEKLY_RAMP_CAP.get(sport, 1.20) if prev else ceiling
        total += min(ceiling, ramp)
    return total


@pytest.mark.parametrize(("athlete", "race", "weeks"), _SAMPLE)
def test_emitted_load_tracks_budget_and_respects_ramp_cap(
    athlete: tuple[str, float, dict[str, int], list[str], float],
    race: tuple[str, list[dict[str, Any]]],
    weeks: int,
) -> None:
    """Propriété (garde-fou #164) : sur n'importe quel profil, n'importe quelle
    course et n'importe quel horizon, chaque semaine émet son budget à +/- 10 %
    (sauf saturation légitime) ET la hausse par sport respecte WEEKLY_RAMP_CAP."""
    plan, phases = _plan_for(athlete, race[1], weeks)
    by_offset: dict[int, list[dict[str, Any]]] = {}
    for s in plan.sessions:
        by_offset.setdefault(int(s["week_offset"]), []).append(s)

    previous: dict[str, float] | None = None
    for offset, phase in phases:
        budget = plan.budget_by_offset[offset]
        training = _training(by_offset[offset])
        emitted = sum(float(s["target_tss"]) for s in training)

        assert emitted <= budget * (1 + LOAD_BUDGET_TOLERANCE) + 1e-6, (
            f"semaine {offset} : {emitted:.1f} TSS émis pour {budget:.1f} budgétés"
        )
        # Borne basse : sauf saturation (plafonds de durée ou cap de progression).
        # 0,5 TSS de mou : les cibles émises sont arrondies au centième.
        floor = min(budget * (1 - LOAD_BUDGET_TOLERANCE), _attainable_tss(training, previous))
        assert emitted >= floor - 0.5, (
            f"semaine {offset} : {emitted:.1f} TSS émis, plancher attendu {floor:.1f}"
        )

        emitted_by_sport = _emitted_by_sport(by_offset[offset])
        for sport, tss in emitted_by_sport.items():
            prev = (previous or {}).get(sport)
            if not prev:
                continue
            cap = WEEKLY_RAMP_CAP.get(sport, 1.20)
            assert tss <= prev * cap + 0.5, (
                f"semaine {offset} : {sport} {prev:.1f} -> {tss:.1f} "
                f"(cap {cap:.2f} => {prev * cap:.1f})"
            )
        if not (phase == "taper" or (offset + 1) % 4 == 0):
            previous = emitted_by_sport
