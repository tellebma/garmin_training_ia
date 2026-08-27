"""Bascule maintien -> course : la forme acquise ne se perd pas (E27.6).

Un athlète qui s'entraîne en maintien pendant des mois, puis se fixe enfin un
objectif, ne doit pas être traité comme un débutant qui découvre le sport. Ce que
sa préparation reçoit en héritage, c'est sa CTL — mesurée sur son historique réel,
pas remise à zéro par le changement de mode.

Ces garanties tenaient déjà par construction (le budget hebdo dérive de la CTL, et
le rabais de reprise ne regarde que les signaux de fatigue), mais rien ne les
protégeait : un futur refactor du planner pouvait les casser en silence.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

from garmin_sync.coach.planner import compute_base_weekly_tss, generate_plan

TODAY = date(2026, 8, 27)
RACE_DAY = TODAY + timedelta(weeks=20)

# L'historique s'arrête il y a 3 jours : une séance dans les 48 h déclencherait
# `recent_long_session`, un rabais de reprise LÉGITIME qui n'a rien à voir avec la
# bascule de mode et masquerait ce que ces tests veulent observer.
_HISTORY_GAP_DAYS = 3


def _profile() -> dict[str, Any]:
    """Profil APRÈS la bascule : créer un objectif force ``training_mode='race'``."""
    return {
        "user_id": "u1",
        "hours_per_week": 8,
        "ftp_watts": None,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
        "training_mode": "race",
        "training_mode_since": TODAY.isoformat(),
    }


def _maintenance_history(*, weekly_tss: float, weeks: int = 12) -> list[dict[str, Any]]:
    """Mois de maintien : cinq sorties par semaine, à charge constante."""
    per_session_s = int(weekly_tss / 5 / 50 * 3600)
    return [
        {
            "start_time": (TODAY - timedelta(weeks=w, days=d + _HISTORY_GAP_DAYS)).isoformat()
            + "T08:00:00+00:00",
            "sport": "run",
            "duration_s": per_session_s,
            "power_avg": None,
            "hr_avg": 140,
            "hr_max": 175,
            "tss": None,
            "elevation_gain_m": 0,
        }
        for w in range(weeks)
        for d in range(5)
    ]


def _db_with_history(activities: list[dict[str, Any]]) -> MagicMock:
    db = MagicMock()
    table = db.table.return_value
    table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
        _profile()
    )
    # Objectif de course tout juste créé : jamais préparé, donc pas d'ancre posée.
    table.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {  # noqa: E501
        "id": "race-1",
        "race_date": RACE_DAY.isoformat(),
        "race_distance": "olympique",
        "discipline": "run",
        "legs": [{"discipline": "run", "distance_km": 10, "elevation_gain_m": 100}],
        "prep_start_date": None,
    }
    # `counted()` ajoute un `.is_("excluded_at", "null")` en bout de chaîne : sans lui
    # dans le mock, la lecture retombe à vide et le planner part en cold start.
    table.select.return_value.eq.return_value.gte.return_value.is_.return_value.execute.return_value.data = (  # noqa: E501
        activities
    )
    table.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
    return db


def _plan(db: MagicMock) -> dict[str, Any]:
    for call in db.table.return_value.insert.call_args_list:
        payload = call.args[0]
        if isinstance(payload, dict) and "weeks_count" in payload:
            return payload
    raise AssertionError("aucun training_plans inséré")


def _first_week_tss(db: MagicMock) -> float:
    """Charge émise sur la première semaine générée du plan."""
    for call in db.table.return_value.insert.call_args_list:
        payload = call.args[0]
        if isinstance(payload, list) and payload:
            first = min(s["week_offset"] for s in payload)
            return round(
                sum(float(s["target_tss"] or 0) for s in payload if s["week_offset"] == first), 2
            )
    raise AssertionError("aucune séance insérée")


def _generate(monkeypatch, activities: list[dict[str, Any]]) -> tuple[dict[str, Any], MagicMock]:
    from garmin_sync.coach import planner as p_mod

    db = _db_with_history(activities)
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: db)
    result = generate_plan("u1", today=TODAY)
    assert result["status"] == "ok"
    return _plan(db), db


def test_the_prep_starts_from_the_fitness_actually_kept(monkeypatch) -> None:
    """Le foncier entretenu se retrouve dans la préparation, pas à la poubelle.

    Même profil, même course, même date : seuls les mois de maintien diffèrent.
    Celui qui a tenu une grosse charge doit hériter d'une CTL — et d'une première
    semaine — nettement supérieures à celui qui a levé le pied.
    """
    kept, kept_db = _generate(monkeypatch, _maintenance_history(weekly_tss=400.0))
    eased_off, eased_db = _generate(monkeypatch, _maintenance_history(weekly_tss=120.0))

    assert kept["ctl_initial"] > eased_off["ctl_initial"] * 1.5, (
        f"CTL héritée {kept['ctl_initial']} contre {eased_off['ctl_initial']} "
        "après un maintien plus léger"
    )
    assert _first_week_tss(kept_db) > _first_week_tss(eased_db), (
        "la préparation ignore la forme déjà acquise : "
        f"{_first_week_tss(kept_db)} TSS contre {_first_week_tss(eased_db)}"
    )


def test_the_switch_itself_is_not_read_as_fatigue(monkeypatch) -> None:
    """Changer de mode n'est pas un signal de fatigue.

    Le rabais prudent de première semaine se déclenche sur ce que disent les
    activités récentes (charge en chute, grosse séance dans les 48 h), jamais sur
    le fait d'avoir basculé de « maintien » vers « course ».
    """
    plan, _ = _generate(monkeypatch, _maintenance_history(weekly_tss=400.0))

    assert plan["params"]["first_week_tss_multiplier"] == 1.0, (
        "la bascule maintien -> course a été prise pour un signal de fatigue"
    )


def test_the_emitted_load_stays_within_the_ctl_derived_budget(monkeypatch) -> None:
    """La CTL mesurée fixe le point de départ, et la semaine émise s'y tient."""
    plan, db = _generate(monkeypatch, _maintenance_history(weekly_tss=400.0))

    budget = compute_base_weekly_tss(ctl=plan["ctl_initial"], hours_per_week=8)
    assert budget > 0
    assert _first_week_tss(db) <= budget * 1.2, (
        f"{_first_week_tss(db)} TSS émis pour un budget dérivé de la CTL de {budget:.0f}"
    )


def test_a_fresh_prep_anchor_is_posted_on_the_new_goal(monkeypatch) -> None:
    """L'ancre de préparation du nouvel objectif est posée au jour de la bascule.

    Elle est immuable ensuite (#123) : c'est elle qui fige le découpage en phases,
    et non `today`, sinon l'horizon rétrécirait à chaque régénération hebdo.
    """
    plan, _ = _generate(monkeypatch, _maintenance_history(weekly_tss=400.0))

    assert plan["params"]["prep_start_date"] == TODAY.isoformat()
    assert plan["start_date"] == TODAY.isoformat()
