"""Fixtures partagées des tests coach.

Le profil de référence est celui de l'owner en prod (audit du 2026-08-14) :
``{run: 1, swim: 2, bike: 4}`` pour un triathlon dont le segment course fait
8 km avec 200 m D+ (25 m/km). C'est ce profil qui a produit 1 seule séance de
qualité sur 41 — d'où les tests #165 / #155 / #156.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest

from garmin_sync.coach.planner import RaceTarget, _build_week_sessions

OWNER_STRENGTHS = {"run": 1, "swim": 2, "bike": 4}
OWNER_SPORTS = ["swim", "bike", "run"]
OWNER_LEGS = [
    {"discipline": "swim", "distance_km": 1.5, "elevation_gain_m": 0},
    {"discipline": "bike", "distance_km": 40.0, "elevation_gain_m": 600},
    {"discipline": "run", "distance_km": 8.0, "elevation_gain_m": 200},
]
OWNER_AVAILABLE_DAYS = ["tue", "wed", "thu", "fri", "sat", "sun"]

OwnerWeek = Callable[..., list[dict[str, Any]]]


@pytest.fixture
def owner_week() -> OwnerWeek:
    """Construit une semaine du plan pour le profil owner."""

    def _build(
        phase: str = "build",
        *,
        strengths: dict[str, int] | None = None,
        weekly_elevation: dict[str, int] | None = None,
        gradient: dict[str, float] | None = None,
        race_dplus: dict[str, int] | None = None,
        progress: float = 1.0,
    ) -> list[dict[str, Any]]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        return _build_week_sessions(
            week_offset=2,
            phase=phase,  # type: ignore[arg-type]
            week_start=week_start,
            sports_in_race=OWNER_SPORTS,
            sports_strengths=strengths or OWNER_STRENGTHS,
            tss_by_sport={"swim": 120.0, "bike": 150.0, "run": 130.0},
            available_days=OWNER_AVAILABLE_DAYS,
            hours_per_week=8,
            is_last_week=False,
            race=RaceTarget(
                day=today + timedelta(days=120),
                sport="triathlon",
                time_shares={"swim": 0.15, "bike": 0.55, "run": 0.30},
                legs=OWNER_LEGS,
                dplus_by_sport=race_dplus,
                gradient_m_per_km=gradient,
            ),
            weekly_elevation_by_sport=weekly_elevation or {},
            progress=progress,
        )

    return _build
