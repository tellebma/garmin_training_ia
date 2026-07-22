"""Régression régénération : la régén hebdo ne doit plus jeter les workouts LLM
déjà générés (et déjà facturés) pour des séances identiques.

Bug prod : chaque dimanche le cron supprimait toutes les séances et les recréait
avec workout=NULL -> le lundi l'athlète retrouvait des séances vides et le LLM
re-facturait exactement les mêmes générations."""

from __future__ import annotations

from typing import Any

from garmin_sync.coach.planner import carry_over_workouts

_WORKOUT = {"summary_md": "déjà généré", "main": []}


def _existing(**overrides: Any) -> dict[str, Any]:
    base = {
        "date": "2026-08-01",
        "sport": "run",
        "session_type": "endurance",
        "target_duration_s": 3600,
        "workout": _WORKOUT,
        "workout_generated_at": "2026-07-20T10:00:00Z",
    }
    base.update(overrides)
    return base


def _new(**overrides: Any) -> dict[str, Any]:
    base = {
        "date": "2026-08-01",
        "sport": "run",
        "session_type": "endurance",
        "target_duration_s": 3600,
    }
    base.update(overrides)
    return base


def test_identical_session_reuses_workout() -> None:
    new_sessions = [_new()]
    reused = carry_over_workouts(new_sessions, [_existing()])
    assert reused == 1
    assert new_sessions[0]["workout"] == _WORKOUT
    assert new_sessions[0]["workout_generated_at"] == "2026-07-20T10:00:00Z"


def test_changed_duration_does_not_reuse_workout() -> None:
    """Durée cible différente = l'enveloppe numérique change, l'ancien workout
    ne colle plus : il ne doit PAS être réutilisé."""
    new_sessions = [_new(target_duration_s=5400)]
    reused = carry_over_workouts(new_sessions, [_existing()])
    assert reused == 0
    assert "workout" not in new_sessions[0]


def test_changed_sport_or_type_does_not_reuse_workout() -> None:
    new_sessions = [_new(sport="bike"), _new(session_type="threshold")]
    assert carry_over_workouts(new_sessions, [_existing()]) == 0


def test_session_without_previous_workout_is_ignored() -> None:
    new_sessions = [_new()]
    assert carry_over_workouts(new_sessions, [_existing(workout=None)]) == 0
    assert "workout" not in new_sessions[0]


def test_only_matching_sessions_are_reused() -> None:
    new_sessions = [_new(), _new(date="2026-08-02"), _new(date="2026-08-03")]
    reused = carry_over_workouts(new_sessions, [_existing(), _existing(date="2026-08-03")])
    assert reused == 2
    assert new_sessions[0]["workout"] == _WORKOUT
    assert "workout" not in new_sessions[1]
    assert new_sessions[2]["workout"] == _WORKOUT
