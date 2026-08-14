"""Régression #158 : le D+ hebdo empilé sur une seule sortie devient irréalisable.

Bug prod (2026-08-08) : `_ELEVATION_SESSION_WEIGHT["long"] = 2.0` concentrait la
cible hebdo sur la séance longue -> 1920 m de D+ sur 2 h de vélo, soit ~960 m/h,
plus raide que la course préparée (~700 m/h sur sa partie vélo). Un plafond de
gradient (m/h) par sport borne désormais chaque séance ; le surplus part sur les
séances qui ont de la marge, et n'est écrêté qu'en dernier recours (avec log).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_sync.coach.planner import (
    ELEVATION_GRADIENT_CAP_M_PER_H,
    cap_session_elevation_gradients,
    compute_weekly_elevation_targets,
    generate_plan,
    session_elevation_cap_m,
)


def _session(
    *,
    sport: str,
    duration_s: int,
    elevation: int | None,
    stype: str = "endurance",
    day: str = "2026-08-08",
) -> dict[str, Any]:
    return {
        "date": day,
        "sport": sport,
        "session_type": stype,
        "target_duration_s": duration_s,
        "target_tss": 100.0,
        "target_elevation_gain_m": elevation,
        "phase": "build",
        "week_offset": 3,
    }


def test_caps_are_sane_and_race_specific() -> None:
    """Les plafonds doivent rester dans l'épure de l'exigence de course (~700 m/h
    vélo) sans descendre sous ce qu'un amateur encaisse réellement."""
    assert 500 <= ELEVATION_GRADIENT_CAP_M_PER_H["bike"] <= 800
    assert 300 <= ELEVATION_GRADIENT_CAP_M_PER_H["run"] <= 600
    # La course à pied grimpe moins vite (en m/h) qu'un vélo sur le même temps.
    assert ELEVATION_GRADIENT_CAP_M_PER_H["run"] < ELEVATION_GRADIENT_CAP_M_PER_H["bike"]
    # Le plafond est proportionnel à la durée.
    assert session_elevation_cap_m("bike", 7200) == 2 * session_elevation_cap_m("bike", 3600)


def test_prod_case_1920m_on_2h_bike_is_capped() -> None:
    """Cas prod : 1920 m sur 2 h (960 m/h) -> ramené au plafond du sport."""
    long_ride = _session(sport="bike", duration_s=7200, elevation=1920, stype="long")
    clipped = cap_session_elevation_gradients([long_ride])

    capped = long_ride["target_elevation_gain_m"]
    assert capped is not None
    assert capped == session_elevation_cap_m("bike", 7200)
    assert capped < 1920
    gradient = capped / 2
    assert gradient <= ELEVATION_GRADIENT_CAP_M_PER_H["bike"]
    # Rien où reporter : le reste est écrêté et remonté à l'appelant.
    assert clipped == 1920 - capped


def test_surplus_is_moved_to_sessions_with_headroom() -> None:
    """Le surplus de la séance longue part sur les séances qui ont de la marge :
    le volume hebdo de D+ est conservé, seule la RÉPARTITION change."""
    long_ride = _session(sport="bike", duration_s=7200, elevation=1920, stype="long")
    endurance = _session(sport="bike", duration_s=7200, elevation=400, day="2026-08-05")
    before = 1920 + 400

    clipped = cap_session_elevation_gradients([long_ride, endurance])

    assert clipped == 0, "tout tenait dans la semaine : rien ne doit être écrêté"
    after = int(long_ride["target_elevation_gain_m"] or 0) + int(
        endurance["target_elevation_gain_m"] or 0
    )
    assert after == before, "le D+ hebdo total doit être conservé"
    assert long_ride["target_elevation_gain_m"] == session_elevation_cap_m("bike", 7200)
    assert int(endurance["target_elevation_gain_m"] or 0) > 400


def test_surplus_never_overflows_the_receiving_sessions() -> None:
    """Le report ne peut pas rendre irréalisable la séance qui reçoit."""
    long_ride = _session(sport="bike", duration_s=7200, elevation=2600, stype="long")
    short = _session(sport="bike", duration_s=3600, elevation=200, day="2026-08-05")

    cap_session_elevation_gradients([long_ride, short])

    for s in (long_ride, short):
        gradient = int(s["target_elevation_gain_m"] or 0) / (s["target_duration_s"] / 3600)
        assert gradient <= ELEVATION_GRADIENT_CAP_M_PER_H["bike"] + 1


def test_week_too_steep_is_clipped_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Une semaine impossible à répartir doit rester cohérente ET bruyante."""
    sessions = [
        _session(sport="bike", duration_s=5400, elevation=3000, stype="long"),
        _session(sport="bike", duration_s=3600, elevation=1500, day="2026-08-05"),
    ]
    with caplog.at_level(logging.WARNING):
        clipped = cap_session_elevation_gradients(sessions)

    assert clipped > 0
    total = sum(int(s["target_elevation_gain_m"] or 0) for s in sessions)
    assert total == 4500 - clipped
    assert any("bike" in r.message or "bike" in str(r.args) for r in caplog.records), (
        "l'écrêtage doit être tracé, pas silencieux"
    )


def test_surplus_split_over_several_sessions_conserves_every_meter() -> None:
    """Report sur 3 séances : les arrondis ne doivent perdre aucun mètre."""
    long_ride = _session(sport="bike", duration_s=7200, elevation=1500, stype="long")
    others = [
        _session(sport="bike", duration_s=3600, elevation=400, day=f"2026-08-0{i}")
        for i in (3, 5, 6)
    ]
    week = [long_ride, *others]
    before = sum(int(s["target_elevation_gain_m"] or 0) for s in week)

    assert cap_session_elevation_gradients(week) == 0
    assert sum(int(s["target_elevation_gain_m"] or 0) for s in week) == before
    assert long_ride["target_elevation_gain_m"] == session_elevation_cap_m("bike", 7200)


def test_sports_do_not_borrow_headroom_from_each_other() -> None:
    """Le report reste intra-sport : un run plat n'absorbe pas le D+ du vélo."""
    ride = _session(sport="bike", duration_s=7200, elevation=1920, stype="long")
    run = _session(sport="run", duration_s=3600, elevation=100, day="2026-08-06")

    cap_session_elevation_gradients([ride, run])

    assert run["target_elevation_gain_m"] == 100


def test_flat_race_sessions_are_left_untouched() -> None:
    """Course plate : aucune cible D+ posée, rien à borner ni à écrêter."""
    sessions = [
        _session(sport="bike", duration_s=7200, elevation=None, stype="long"),
        _session(sport="run", duration_s=3600, elevation=None),
    ]
    assert cap_session_elevation_gradients(sessions) == 0
    assert all(s["target_elevation_gain_m"] is None for s in sessions)


def test_sessions_under_the_cap_are_not_inflated() -> None:
    """Sans surplus à placer, une séance raisonnable garde sa cible."""
    ride = _session(sport="bike", duration_s=7200, elevation=600, stype="long")
    assert cap_session_elevation_gradients([ride]) == 0
    assert ride["target_elevation_gain_m"] == 600


_ELEV_PHASES: list[tuple[int, Any]] = [
    (0, "base"),
    (1, "base"),
    (2, "base"),
    (3, "build"),
    (4, "build"),
    (5, "build"),
    (6, "peak"),
    (7, "taper"),
]


def test_weekly_progression_toward_peak_is_untouched() -> None:
    """Non-régression #131 : le plafond agit sur la RÉPARTITION intra-semaine,
    jamais sur la cible hebdo ni sur la progression vers le pic."""
    targets = [
        compute_weekly_elevation_targets(
            race_dplus_by_sport={"bike": 2000},
            week_offset=w,
            phases=_ELEV_PHASES,
            observed_weekly_dplus={"bike": 800},
        )["bike"]
        for w, _ in _ELEV_PHASES[:-1]
    ]
    assert targets == sorted(targets)
    assert targets[-1] >= 1999


def _plan_sessions(monkeypatch: pytest.MonkeyPatch, *, race_dplus: int) -> list[dict[str, Any]]:
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
        "race_date": (date.today() + timedelta(days=48)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 53, "elevation_gain_m": race_dplus},
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

    assert generate_plan("u1")["status"] == "ok"
    return captured


def test_generated_plan_has_no_unrealistic_gradient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bout en bout : aucune séance du plan ne dépasse le plafond de son sport."""
    sessions = _plan_sessions(monkeypatch, race_dplus=2200)
    with_dplus = [s for s in sessions if s.get("target_elevation_gain_m")]
    assert with_dplus, "le plan doit bien poser des cibles de D+"
    for s in with_dplus:
        hours = float(s["target_duration_s"]) / 3600
        cap = ELEVATION_GRADIENT_CAP_M_PER_H.get(str(s["sport"]), 500.0)
        assert s["target_elevation_gain_m"] / hours <= cap + 1, (
            f"{s['date']} {s['sport']} : {s['target_elevation_gain_m']} m sur {hours:.1f} h"
        )


def test_flat_race_plan_sets_no_elevation_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Course plate (vélo à 50 m) : aucune cible D+ vélo dans le plan."""
    sessions = _plan_sessions(monkeypatch, race_dplus=50)
    bike = [s for s in sessions if s["sport"] == "bike"]
    assert bike
    assert all(s["target_elevation_gain_m"] is None for s in bike)
