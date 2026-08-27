"""Entraînement sans objectif daté : plan produit, et charge qui ne s'emballe pas (E27)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_sync.coach.banister import CTL_TAU
from garmin_sync.coach.cycles import CYCLE_WEEKS, cycle_load_multipliers, cycle_week
from garmin_sync.coach.planner import (
    compute_base_weekly_tss,
    generate_plan,
    observed_sport_time_shares,
)

TODAY = date(2026, 8, 25)  # un mardi


def _profile(mode: str, since: date | None = TODAY) -> dict[str, Any]:
    return {
        "user_id": "u1",
        "hours_per_week": 8,
        "ftp_watts": None,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
        "training_mode": mode,
        "training_mode_since": since.isoformat() if since else None,
    }


def _fake_db(profile: dict[str, Any], *, past_race: dict[str, Any] | None = None) -> MagicMock:
    """DB minimale : profil, pas de course primaire, insertions qui répondent un id."""
    db = MagicMock()
    table = db.table.return_value
    table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
        profile
    )
    # Dernière course passée (mode cycle) : chaîne .lte().order().limit().execute()
    order_chain = table.select.return_value.eq.return_value.lte.return_value.order.return_value
    order_chain.limit.return_value.execute.return_value.data = [past_race] if past_race else []
    # Course primaire (mode race) : absente.
    table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None  # noqa: E501
    table.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
    return db


def _inserted_plan(db: MagicMock) -> dict[str, Any]:
    for call in db.table.return_value.insert.call_args_list:
        payload = call.args[0]
        if isinstance(payload, dict) and "weeks_count" in payload:
            return payload
    raise AssertionError("aucun training_plans inséré")


def _inserted_sessions(db: MagicMock) -> list[dict[str, Any]]:
    for call in db.table.return_value.insert.call_args_list:
        payload = call.args[0]
        if isinstance(payload, list) and payload:
            return payload
    return []


@pytest.mark.parametrize("mode", ["maintain", "improve"])
def test_a_plan_is_produced_without_any_race(monkeypatch, mode: str) -> None:
    """Le trou qu'on répare : sans course, l'app ne générait plus rien."""
    from garmin_sync.coach import planner as p_mod

    db = _fake_db(_profile(mode))
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: db)

    result = generate_plan("u1", today=TODAY)

    assert result["status"] == "ok"
    assert result["mode"] == mode
    assert result["sessions_count"] > 0
    plan = _inserted_plan(db)
    assert plan["race_goal_id"] is None
    assert plan["weeks_count"] == CYCLE_WEEKS
    assert plan["params"]["training_mode"] == mode


def test_a_past_race_no_longer_freezes_the_app(monkeypatch) -> None:
    """Mode 'race' + course passée : plan de maintien, et la question reste posée."""
    from garmin_sync.coach import planner as p_mod

    db = MagicMock()
    table = db.table.return_value
    table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
        _profile("race")
    )
    table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {  # noqa: E501
        "id": "race-1",
        "race_date": (TODAY - timedelta(days=30)).isoformat(),
        "race_distance": "olympique",
        "discipline": "triathlon",
        "legs": [{"discipline": "run", "distance_km": 10}],
        "prep_start_date": None,
    }
    table.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: db)

    result = generate_plan("u1", today=TODAY)

    assert result["status"] == "ok"
    assert result["mode"] == "maintain"
    assert _inserted_plan(db)["race_goal_id"] is None


def test_recovery_after_a_recent_race_beats_the_chosen_mode(monkeypatch) -> None:
    """Récupération imposée : même en progression, on ne recharge pas à J+2."""
    from garmin_sync.coach import planner as p_mod

    race_day = TODAY - timedelta(days=2)
    past_race = {
        "id": "race-1",
        "race_date": race_day.isoformat(),
        "race_distance": "half_ironman",
    }
    db = _fake_db(_profile("improve"), past_race=past_race)
    # Activités rattachées à la course : 5 h d'effort -> 2 semaines de récup.
    counted_chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    counted_chain.execute.return_value.data = [{"duration_s": 5 * 3600}]
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: db)

    result = generate_plan("u1", today=TODAY)

    assert result["status"] == "ok"
    plan = _inserted_plan(db)
    assert plan["params"]["recovery_until"] == (race_day + timedelta(days=14)).isoformat()


def test_no_hard_session_during_the_recovery_window(monkeypatch) -> None:
    from garmin_sync.coach import planner as p_mod

    race_day = TODAY - timedelta(days=1)
    db = _fake_db(
        _profile("improve"),
        past_race={
            "id": "race-1",
            "race_date": race_day.isoformat(),
            "race_distance": "olympique",
        },
    )
    counted_chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    counted_chain.execute.return_value.data = [{"duration_s": 3 * 3600}]
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: db)

    generate_plan("u1", today=TODAY)

    window_end = race_day + timedelta(days=7)
    sessions = _inserted_sessions(db)
    in_window = [
        s for s in sessions if s.get("date") and date.fromisoformat(s["date"]) <= window_end
    ]
    after = [s for s in sessions if s.get("date") and date.fromisoformat(s["date"]) > window_end]
    assert in_window, "la fenêtre de récup doit contenir des séances, pas être vide"

    # Ce que le nom du test promet : aucune qualité, aucune longue.
    assert {s["session_type"] for s in in_window} <= {"recovery", "endurance", "rest"}
    # ... et la restriction s'arrête avec la fenêtre, sinon on ne s'entraîne plus jamais.
    assert any(s["session_type"] not in {"recovery", "endurance", "rest"} for s in after)


# --------------------------------------------------------------------------------------
# Le test qui protège le vrai risque : la double rampe.
# --------------------------------------------------------------------------------------


def _simulate_weeks(mode: str, *, weeks: int, ctl0: float, hours_per_week: float) -> list[float]:
    """Rejoue N régénérations hebdomadaires, en réinjectant la CTL produite.

    Reproduit fidèlement la boucle réelle : chaque semaine, ``base_weekly`` est
    recalculé depuis la CTL MESURÉE du moment, puis le multiplicateur de la position
    courante dans le cycle est appliqué. Renvoie la charge hebdo demandée, semaine
    après semaine.
    """
    since = TODAY
    ctl = ctl0
    demanded: list[float] = []
    for week in range(weeks):
        today = since + timedelta(weeks=week)
        base_weekly = compute_base_weekly_tss(ctl=ctl, hours_per_week=hours_per_week)
        multiplier = cycle_load_multipliers(
            mode, start_cycle_week=cycle_week(since, today), weeks=1
        )[0]
        weekly = base_weekly * multiplier
        demanded.append(weekly)
        # La semaine est encaissée telle quelle : CTL mise à jour jour par jour.
        for _ in range(7):
            ctl += (weekly / 7 - ctl) / CTL_TAU
    return demanded


def test_improve_never_compounds_the_ramp_twice() -> None:
    """Six régénérations d'affilée ne doivent pas dépasser +5 %/semaine.

    Sans cette garantie, la rampe s'appliquerait à une CTL qui a DÉJÀ monté de 5 % :
    deux fois la même progression, invisible en revue de code, et une surcharge
    constatée seulement trois semaines plus tard en production.
    """
    weeks = 6
    demanded = _simulate_weeks("improve", weeks=weeks, ctl0=50.0, hours_per_week=20)
    theoretical_max = demanded[0] * 1.05 ** (weeks - 1) * 1.02  # tolérance 2 %
    assert max(demanded) <= theoretical_max


def test_maintain_holds_the_ctl_within_five_percent() -> None:
    """Maintenir, c'est produire 7 x CTL par semaine — le point fixe du modèle."""
    ctl = 50.0
    since = TODAY
    for week in range(8):
        today = since + timedelta(weeks=week)
        base_weekly = compute_base_weekly_tss(ctl=ctl, hours_per_week=20)
        multiplier = cycle_load_multipliers(
            "maintain", start_cycle_week=cycle_week(since, today), weeks=1
        )[0]
        weekly = base_weekly * multiplier
        for _ in range(7):
            ctl += (weekly / 7 - ctl) / CTL_TAU
    assert 47.5 <= ctl <= 52.5


def test_the_hours_budget_still_caps_a_long_progression() -> None:
    """La rampe converge vers le budget déclaré et ne le dépasse jamais."""
    demanded = _simulate_weeks("improve", weeks=40, ctl0=20.0, hours_per_week=6)
    assert max(demanded) <= 6 * 45  # weekly_tss_cap_from_hours


# --------------------------------------------------------------------------------------
# Disciplines : sans course, on maintient ce qui est réellement pratiqué.
# --------------------------------------------------------------------------------------


def test_observed_shares_follow_what_the_athlete_actually_does() -> None:
    activities = [
        {"start_time": "2026-08-20T08:00:00Z", "sport": "running", "duration_s": 3600},
        {"start_time": "2026-08-18T08:00:00Z", "sport": "cycling", "duration_s": 3600},
    ]
    shares = observed_sport_time_shares(activities, today=TODAY)
    assert set(shares) == {"run", "bike"}
    assert shares["run"] == pytest.approx(0.5)


def test_a_single_token_swim_does_not_earn_a_weekly_swim_slot() -> None:
    activities = [
        {"start_time": "2026-08-20T08:00:00Z", "sport": "running", "duration_s": 10 * 3600},
        {"start_time": "2026-08-18T08:00:00Z", "sport": "lap_swimming", "duration_s": 900},
    ]
    assert set(observed_sport_time_shares(activities, today=TODAY)) == {"run"}


def test_without_history_declared_disciplines_keep_the_plan_alive() -> None:
    """Un plan de maintien sans discipline serait un plan vide."""
    assert observed_sport_time_shares([], today=TODAY) == {}
