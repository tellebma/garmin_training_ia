"""Séances d'enchaînement (brick) — issue #154.

Prod : 0 brick sur les 41 séances d'une prépa triathlon dont l'épreuve enchaîne
8 km de course après 47 km de vélo. Le brick doit être planifié en build/peak,
et se SUBSTITUER au volume vélo + CAP au lieu de s'y ajouter.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise

import pytest

from garmin_sync.coach.planner import (
    TrainingTarget,
    WeekSlot,
    _build_week_sessions,
    _tss_with_brick_share,
    race_has_bike_run_transition,
)

TRIATHLON_LEGS = [
    {"discipline": "swim", "distance_km": 1.4},
    {"discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000},
    {"discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
]
IMPACT_SPORTS = {"run", "brick"}


def _week(
    phase: str,
    *,
    has_transition: bool = True,
    week_offset: int = 0,
) -> list[dict[str, object]]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    return _build_week_sessions(
        slot=WeekSlot(
            offset=week_offset,
            phase=phase,  # type: ignore[arg-type],
            start=week_start,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 100.0, "bike": 120.0, "run": 110.0},
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        hours_per_week=10,
        target=TrainingTarget(
            race_day=today + timedelta(days=180),
            sport="triathlon",
            has_bike_run_transition=has_transition,
        ),
    )


def _sports(sessions: list[dict[str, object]]) -> list[str]:
    return [str(s["sport"]) for s in sessions if s["sport"] != "rest"]


def test_race_has_bike_run_transition_for_triathlon() -> None:
    assert race_has_bike_run_transition(TRIATHLON_LEGS) is True


def test_race_has_bike_run_transition_for_duathlon() -> None:
    legs = [
        {"discipline": "run", "distance_km": 5},
        {"discipline": "bike", "distance_km": 20},
        {"discipline": "run", "distance_km": 2.5},
    ]
    assert race_has_bike_run_transition(legs) is True


def test_race_has_no_bike_run_transition_for_single_discipline() -> None:
    assert race_has_bike_run_transition([{"discipline": "run", "distance_km": 42.2}]) is False
    assert race_has_bike_run_transition([]) is False


def test_race_has_no_bike_run_transition_for_aquathlon() -> None:
    """Le brick outillé ici est un vélo->CAP : un swim->run n'y donne pas droit."""
    legs = [{"discipline": "swim", "distance_km": 1}, {"discipline": "run", "distance_km": 5}]
    assert race_has_bike_run_transition(legs) is False


@pytest.mark.parametrize("phase", ["build", "peak"])
def test_build_week_plans_one_brick_in_build_and_peak(phase: str) -> None:
    sessions = _week(phase)
    bricks = [s for s in sessions if s["sport"] == "brick"]
    assert len(bricks) == 1
    brick = bricks[0]
    assert int(brick["target_duration_s"] or 0) > 0
    assert float(brick["target_tss"] or 0) > 0


@pytest.mark.parametrize("phase", ["base", "taper"])
def test_no_brick_outside_build_and_peak(phase: str) -> None:
    assert "brick" not in _sports(_week(phase))


def test_no_brick_for_single_discipline_race() -> None:
    assert "brick" not in _sports(_week("build", has_transition=False))


def test_brick_week_keeps_one_session_per_race_discipline() -> None:
    sports = _sports(_week("build"))
    for discipline in ("swim", "bike", "run"):
        assert discipline in sports


def test_brick_week_has_no_back_to_back_impact_days() -> None:
    sessions = [s for s in _week("build") if s["sport"] != "rest"]
    ordered = [str(s["sport"]) for s in sorted(sessions, key=lambda s: str(s["date"]))]
    for a, b in pairwise(ordered):
        assert not (a in IMPACT_SPORTS and b in IMPACT_SPORTS)


def test_brick_duration_stays_credible() -> None:
    brick = next(s for s in _week("build") if s["sport"] == "brick")
    assert 60 * 60 <= int(brick["target_duration_s"] or 0) <= 180 * 60


def test_brick_tss_is_taken_from_bike_and_run_not_added() -> None:
    """Substitution : le budget vélo + CAP + brick est conservé, swim intact."""
    before = {"swim": 100.0, "bike": 120.0, "run": 110.0}
    after = _tss_with_brick_share(before, {"swim": 1, "bike": 2, "run": 1, "brick": 1})
    assert after["swim"] == 100.0
    assert after["brick"] > 0
    assert after["bike"] < before["bike"]
    assert after["run"] < before["run"]
    assert after["bike"] + after["run"] + after["brick"] == pytest.approx(230.0, abs=0.05)


def test_tss_split_is_a_noop_without_brick() -> None:
    before = {"swim": 100.0, "bike": 120.0, "run": 110.0}
    assert _tss_with_brick_share(before, {"swim": 1, "bike": 2, "run": 1}) == before


def test_tss_split_is_a_noop_without_bike_or_run_volume() -> None:
    """Rien à prélever (aucun budget vélo/CAP) : le budget reste inchangé."""
    before = {"swim": 100.0}
    assert _tss_with_brick_share(before, {"swim": 1, "brick": 1}) == before


def test_brick_week_stays_within_the_declared_hours_budget() -> None:
    """Le brick remplace une séance : il ne rallonge pas la semaine au-delà du budget."""
    planned_h = sum(int(s["target_duration_s"] or 0) for s in _week("build")) / 3600
    assert planned_h <= 10
