"""Régression géométrie du plan : couverture jusqu'au jour de course, pas de séance
dans le passé, séance course émise. Voir bug prod 2026-07 (plan fini 13 j avant la
course, aucune séance 'race', semaine 0 déjà passée)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

from garmin_sync.coach.phases import compute_phases
from garmin_sync.coach.planner import generate_plan


def _run_generate_plan_capturing_sessions(
    monkeypatch: Any, *, race_in_days: int
) -> list[dict[str, Any]]:
    """Run generate_plan with a fixed race offset and return the planned_sessions
    payload that would be inserted."""
    from garmin_sync.coach import planner as p_mod

    captured: list[dict[str, Any]] = []
    profile = {
        "user_id": "u1",
        "hours_per_week": 6,
        "ftp_watts": 200,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    }
    race = {
        "id": "rg-1",
        "race_date": (date.today() + timedelta(days=race_in_days)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 53, "elevation_gain_m": 2200},
            {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
        ],
    }

    def _capture_sessions(payload: list[dict[str, Any]]) -> MagicMock:
        captured.extend(payload)
        m = MagicMock()
        m.execute.return_value.data = []
        return m

    def _table_router(table_name: str) -> MagicMock:
        m = MagicMock()
        if table_name == "athlete_profiles":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
                profile
            )
        elif table_name == "race_goals":
            m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = race  # noqa: E501
        elif table_name == "activities":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            m.update.return_value.in_.return_value.execute.return_value = MagicMock()
            m.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
        elif table_name == "planned_sessions":
            m.delete.return_value.in_.return_value.execute.return_value = MagicMock()
            m.insert.side_effect = _capture_sessions
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u1")
    assert result["status"] == "ok"
    return captured


def test_compute_phases_ceils_partial_final_week() -> None:
    """Une course à 34 jours (≈4,9 sem) doit produire 5 semaines, pas 4 :
    la semaine partielle qui contient la course ne doit pas être jetée."""
    start = date(2026, 1, 1)
    assert len(compute_phases(start, start + timedelta(days=34))) == 5
    # Course à 8 jours = 2 semaines (pas 1 qui raterait le jour de course).
    assert len(compute_phases(start, start + timedelta(days=8))) == 2
    # Multiples exacts inchangés (rétro-compat avec test_phases.py).
    assert len(compute_phases(start, start + timedelta(weeks=8))) == 8


def test_plan_last_session_is_race_day(monkeypatch) -> None:
    """Le plan doit aller JUSQU'À la course, avec une séance 'race' ce jour-là."""
    race_date = (date.today() + timedelta(days=34)).isoformat()
    sessions = _run_generate_plan_capturing_sessions(monkeypatch, race_in_days=34)

    dates = [s["date"] for s in sessions]
    assert max(dates) == race_date, (
        f"dernière séance {max(dates)} != jour de course {race_date} "
        "(plan qui s'arrête avant la course)"
    )
    race_sessions = [s for s in sessions if s["session_type"] == "race"]
    assert len(race_sessions) == 1, "il doit y avoir exactement une séance 'race'"
    assert race_sessions[0]["date"] == race_date
    assert race_sessions[0]["phase"] == "race"


def test_race_day_of_triathlon_is_not_a_swim_session(monkeypatch) -> None:
    """Régression #135 : le jour de course d'un triathlon portait le sport du
    premier leg (swim). Il doit porter la discipline du race_goal."""
    sessions = _run_generate_plan_capturing_sessions(monkeypatch, race_in_days=34)
    race_sessions = [s for s in sessions if s["session_type"] == "race"]
    assert len(race_sessions) == 1
    assert race_sessions[0]["sport"] == "triathlon"


def test_plan_has_no_session_before_today(monkeypatch) -> None:
    """Aucune séance mort-née dans le passé (semaine 0 ancrée au passé)."""
    today = date.today().isoformat()
    sessions = _run_generate_plan_capturing_sessions(monkeypatch, race_in_days=34)
    past = [s["date"] for s in sessions if s["date"] < today]
    assert past == [], f"séances datées avant aujourd'hui : {past}"


def test_plan_final_week_is_taper(monkeypatch) -> None:
    """La dernière semaine (hors jour de course) doit être du taper, pas du build."""
    sessions = _run_generate_plan_capturing_sessions(monkeypatch, race_in_days=34)
    last_offset = max(s["week_offset"] for s in sessions)
    last_week_non_race = [
        s for s in sessions if s["week_offset"] == last_offset and s["session_type"] != "race"
    ]
    assert last_week_non_race, "la dernière semaine doit contenir des séances de taper"
    assert all(s["phase"] == "taper" for s in last_week_non_race)
