"""Régression #123 : la périodisation doit être ancrée sur un début de
préparation IMMUABLE (race_goals.prep_start_date), pas recalculée depuis
`today` à chaque régénération hebdo.

Bug prod : l'horizon rétrécissait d'une semaine chaque dimanche -> l'athlète
restait perpétuellement dans les premières phases (jamais de peak, retour
build -> base à J-21 de la course), et les week_offset repartaient de 0 à
chaque régénération (deux « semaine 0 » dans le même plan).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

from garmin_sync.coach.planner import generate_plan

_PHASE_ORDER = {"base": 0, "build": 1, "peak": 2, "taper": 3, "race": 4}


def _make_race(*, race_date: date, prep_start: date | None) -> dict[str, Any]:
    return {
        "id": "rg-anchor",
        "race_date": race_date.isoformat(),
        "prep_start_date": prep_start.isoformat() if prep_start else None,
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000},
            {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
        ],
    }


def _run_plan(
    monkeypatch: Any,
    *,
    today: date,
    race: dict[str, Any],
    past_sessions: list[dict[str, Any]] | None = None,
    previous_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run generate_plan against mocks; capture inserted sessions + updates."""
    from garmin_sync.coach import planner as p_mod

    captured: dict[str, Any] = {
        "sessions": [],
        "race_updates": [],
        "ps_updates": [],
        "plan_inserts": [],
    }
    profile = {
        "user_id": "u1",
        "hours_per_week": 8,
        "ftp_watts": None,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 1},
        "available_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    }

    def _capture_sessions(payload: list[dict[str, Any]]) -> MagicMock:
        captured["sessions"].extend(payload)
        m = MagicMock()
        m.execute.return_value.data = []
        return m

    rg_mock = MagicMock()
    rg_chain = rg_mock.select.return_value.eq.return_value.eq.return_value
    rg_chain.maybe_single.return_value.execute.return_value.data = race
    rg_mock.update.side_effect = lambda payload: (
        captured["race_updates"].append(payload),
        MagicMock(),
    )[1]

    tp_mock = MagicMock()
    tp_mock.select.return_value.eq.return_value.execute.return_value.data = previous_plans or []

    def _capture_plan_insert(payload: dict[str, Any]) -> MagicMock:
        captured["plan_inserts"].append(payload)
        m = MagicMock()
        m.execute.return_value.data = [{"id": "plan-new"}]
        return m

    tp_mock.insert.side_effect = _capture_plan_insert

    ps_mock = MagicMock()
    # Requête carry-over des workouts déjà payés (futures sessions).
    ps_mock.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
    # Requête des séances passées re-parentées (réalignement week_offset).
    ps_mock.select.return_value.eq.return_value.lt.return_value.execute.return_value.data = (
        past_sessions or []
    )
    ps_mock.update.side_effect = lambda payload: (
        captured["ps_updates"].append(payload),
        MagicMock(),
    )[1]
    ps_mock.insert.side_effect = _capture_sessions

    def _table_router(table_name: str) -> MagicMock:
        m = MagicMock()
        if table_name == "athlete_profiles":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
                profile
            )
        elif table_name == "race_goals":
            return rg_mock
        elif table_name == "activities":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            return tp_mock
        elif table_name == "planned_sessions":
            return ps_mock
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u1", today=today)
    assert result["status"] == "ok"
    captured["result"] = result
    return captured


def test_anchored_prep_reaches_late_phases(monkeypatch) -> None:
    """À J-27 avec un prep démarré 9 semaines plus tôt, l'athlète doit être en
    build/peak/taper — pas remis en `base` comme en prod."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(days=27)
    prep_start = today - timedelta(weeks=9)
    cap = _run_plan(monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=prep_start))

    phases = {s["phase"] for s in cap["sessions"]}
    assert "base" not in phases, f"retour en base à J-27 : {phases}"
    assert "peak" in phases, f"le peak doit exister en fin de prep : {phases}"
    # week_offset ancré : la semaine courante n'est PAS la semaine 0.
    assert min(s["week_offset"] for s in cap["sessions"]) >= 8


def test_regeneration_keeps_calendar_week_phase_stable(monkeypatch) -> None:
    """Régénérer à S puis S+2 (même ancre) doit donner la même phase pour une
    même semaine calendaire : la progression est monotone, jamais de retour
    build -> base."""
    race_date = date(2026, 10, 25)
    prep_start = date(2026, 7, 6)

    def _phase_by_week(today: date) -> dict[int, str]:
        cap = _run_plan(
            monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=prep_start)
        )
        out: dict[int, str] = {}
        for s in cap["sessions"]:
            if s["phase"] != "race":
                out.setdefault(s["week_offset"], s["phase"])
        return out

    run_1 = _phase_by_week(date(2026, 8, 3))
    run_2 = _phase_by_week(date(2026, 8, 17))

    common = set(run_1) & set(run_2)
    assert common, "les deux runs doivent partager des semaines calendaires"
    for offset in common:
        assert run_1[offset] == run_2[offset], (
            f"semaine {offset} : phase {run_1[offset]} devenue {run_2[offset]}"
        )
    # La semaine courante avance dans la périodisation (jamais en arrière).
    assert min(run_2) > min(run_1)


def test_first_generation_persists_prep_start_date(monkeypatch) -> None:
    """Sans ancre existante, la première génération doit la poser (= today)."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(weeks=8)
    cap = _run_plan(monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=None))

    assert {"prep_start_date": today.isoformat()} in cap["race_updates"]
    # Ancre = today -> comportement identique à l'ancien (semaine courante = 0).
    assert min(s["week_offset"] for s in cap["sessions"]) == 0


def test_existing_anchor_is_not_overwritten(monkeypatch) -> None:
    """L'ancre est immuable : une régénération ne doit jamais la réécrire."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(days=27)
    prep_start = today - timedelta(weeks=9)
    cap = _run_plan(monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=prep_start))

    assert cap["race_updates"] == [], f"l'ancre a été réécrite : {cap['race_updates']}"


def test_week_offsets_are_unique_and_consistent_with_dates(monkeypatch) -> None:
    """Corollaire #123 : chaque date doit mapper sur UN week_offset dérivé de la
    grille ancrée (plus de doublons « semaine 0 » dans un même plan)."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(days=27)
    prep_start = today - timedelta(weeks=9)
    cap = _run_plan(monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=prep_start))

    weeks_count = cap["result"]["weeks_count"]
    grid_start = race_date - timedelta(days=weeks_count * 7 - 1)
    for s in cap["sessions"]:
        expected = (date.fromisoformat(s["date"]) - grid_start).days // 7
        assert s["week_offset"] == expected, (
            f"{s['date']} : week_offset {s['week_offset']} != {expected}"
        )


def test_plan_params_expose_declared_vs_planned_hours(monkeypatch) -> None:
    """#129 : l'écart budget déclaré / volume planifié doit être visible dans
    params (l'UI peut alors l'expliquer au lieu de laisser deviner)."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(weeks=12)
    cap = _run_plan(monkeypatch, today=today, race=_make_race(race_date=race_date, prep_start=None))

    params = cap["plan_inserts"][0]["params"]
    assert params["declared_hours_per_week"] == 8
    assert params["planned_hours_reference_week"] > 0


def test_reparented_past_sessions_get_realigned_week_offsets(monkeypatch) -> None:
    """Les séances passées re-parentées portaient les week_offset de l'ancien
    plan (doublons). Elles doivent être réalignées sur la grille ancrée."""
    today = date(2026, 8, 2)
    race_date = today + timedelta(days=27)
    prep_start = today - timedelta(weeks=9)
    weeks_count = 13  # ceil(90/7)
    grid_start = race_date - timedelta(days=weeks_count * 7 - 1)

    past = [
        {"id": "s-old-1", "date": (today - timedelta(days=10)).isoformat()},
        {"id": "s-old-2", "date": (today - timedelta(days=3)).isoformat()},
    ]
    cap = _run_plan(
        monkeypatch,
        today=today,
        race=_make_race(race_date=race_date, prep_start=prep_start),
        past_sessions=past,
        previous_plans=[{"id": "old-plan"}],
    )

    expected_offsets = {
        (date.fromisoformat(p["date"]) - grid_start).days // 7 for p in past
    }
    realigned = {u["week_offset"] for u in cap["ps_updates"] if "week_offset" in u}
    assert realigned == expected_offsets, (
        f"offsets réalignés {realigned} != attendus {expected_offsets}"
    )
