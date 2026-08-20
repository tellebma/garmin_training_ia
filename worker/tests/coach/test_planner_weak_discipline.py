"""#156 : traiter la discipline faible déclarée.

Profil owner : ``run = 1``, point faible explicite, qui recevait +25 % de volume
et 0 % d'intensité — « beaucoup de kilomètres lents ». Et une cible de D+ course
à pied de 40 à 116 m pour une épreuve qui demande 200 m sur 8 km (25 m/km).
"""

from __future__ import annotations

from typing import Any

from garmin_sync.coach.planner import (
    _QUALITY_SESSION_TYPES,
    apply_race_gradient_floor,
    race_gradient_m_per_km,
)

from .conftest import OWNER_LEGS, OwnerWeek

HILLY = {"weekly_elevation": {"run": 120, "bike": 600, "swim": 0}, "race_dplus": {"run": 200}}


def _quality(sessions: list[dict[str, Any]], sport: str | None = None) -> list[dict[str, Any]]:
    return [
        s
        for s in sessions
        if s["session_type"] in _QUALITY_SESSION_TYPES and (sport is None or s["sport"] == sport)
    ]


def _max_gradient(sessions: list[dict[str, Any]], sport: str) -> float:
    hilly = [
        s for s in sessions if s["sport"] == sport and (s.get("target_elevation_gain_m") or 0) > 0
    ]
    assert hilly, f"aucune séance {sport} ne porte de D+"
    return max(s["target_elevation_gain_m"] / (s["target_duration_s"] / 3600) for s in hilly)


# --- la nature des séances, pas seulement leur nombre ------------------------


def test_weak_discipline_is_no_longer_the_only_one_without_intensity(
    owner_week: OwnerWeek,
) -> None:
    sessions = owner_week("build")
    assert _quality(sessions, "run"), "le point faible reste sans aucune qualité"


def test_weak_discipline_quality_is_dosed_not_hard(owner_week: OwnerWeek) -> None:
    """Le point faible reçoit de la qualité LÉGÈRE, pas un 3x10' de seuil."""
    sessions = owner_week("build")
    assert {s["session_type"] for s in _quality(sessions, "run")} <= {"strides"}


def test_weak_discipline_with_enough_volume_gets_a_second_quality_session(
    owner_week: OwnerWeek,
) -> None:
    """Son surplus de volume (+25 %) ne doit pas être QUE du kilomètre lent."""
    sessions = owner_week("build", strengths={"run": 1, "swim": 3, "bike": 3})
    run_sessions = [s for s in sessions if s["sport"] == "run"]
    if len(run_sessions) >= 3:
        assert len(_quality(sessions, "run")) >= 2


def test_weak_discipline_is_served_before_the_strong_one(owner_week: OwnerWeek) -> None:
    """Servi en dernier, le point faible se retrouvait coincé sans créneau."""
    sessions = owner_week("build")
    assert len(_quality(sessions, "run")) >= len(_quality(sessions, "bike")) - 1


# --- spécificité terrain : le D+ course à pied vise l'épreuve ----------------


def test_race_gradient_is_computed_per_km_not_as_a_total() -> None:
    gradient = race_gradient_m_per_km(OWNER_LEGS)
    assert round(gradient["run"], 1) == 25.0  # 200 m / 8 km
    assert round(gradient["bike"], 1) == 15.0
    assert "swim" not in gradient  # aucun D+ : rien à préparer


def test_run_elevation_target_reaches_the_race_gradient_in_build(owner_week: OwnerWeek) -> None:
    sessions = owner_week("build", gradient={"run": 25.0, "bike": 15.0}, **HILLY)
    # 25 m/km x 10 km/h de vitesse de référence = 250 m/h (contre ~6 m/km émis).
    assert _max_gradient(sessions, "run") >= 200


def test_run_elevation_target_reaches_the_race_gradient_in_peak(owner_week: OwnerWeek) -> None:
    sessions = owner_week("peak", gradient={"run": 25.0}, **HILLY)
    assert _max_gradient(sessions, "run") >= 200


def test_race_gradient_floor_does_not_apply_in_base(owner_week: OwnerWeek) -> None:
    sessions = owner_week("base", gradient={"run": 25.0, "bike": 15.0}, **HILLY)
    assert _max_gradient(sessions, "run") < 250, "la spécificité s'impose en build/peak seulement"


def test_race_gradient_floor_ramps_up_during_build(owner_week: OwnerWeek) -> None:
    early = owner_week("build", gradient={"run": 25.0}, progress=0.0, **HILLY)
    late = owner_week("build", gradient={"run": 25.0}, progress=1.0, **HILLY)
    assert _max_gradient(early, "run") < _max_gradient(late, "run")


def test_race_gradient_floor_respects_the_session_gradient_cap(owner_week: OwnerWeek) -> None:
    """Une course absurde (200 m/km) ne produit pas une séance injouable (#158)."""
    sessions = owner_week("build", gradient={"run": 200.0}, **HILLY)
    assert _max_gradient(sessions, "run") <= 500


def test_race_gradient_floor_never_exceeds_150_percent_of_the_race_dplus() -> None:
    sessions = [
        {
            "sport": "run",
            "session_type": "long",
            "target_duration_s": 5400,
            "target_elevation_gain_m": 50,
        }
    ]
    apply_race_gradient_floor(
        sessions,
        gradient_by_sport={"run": 25.0},
        race_dplus_by_sport={"run": 200},
        phase="build",
        progress=1.0,
    )
    assert sessions[0]["target_elevation_gain_m"] == 300  # 200 m x 1,5


def test_race_gradient_floor_is_a_noop_without_a_gradient() -> None:
    sessions = [
        {
            "sport": "run",
            "session_type": "long",
            "target_duration_s": 3600,
            "target_elevation_gain_m": 40,
        }
    ]
    apply_race_gradient_floor(sessions, gradient_by_sport={}, phase="build")
    assert sessions[0]["target_elevation_gain_m"] == 40
