"""#155 : garantir un volume de qualité par discipline.

Preuve prod : 41 séances, 1 seule ``threshold``, 0 fractionné, 0 PMA — le reste
en endurance/récupération. Le plan ne ressemblait pas à une préparation.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise
from typing import Any

from garmin_sync.coach.planner import (
    _QUALITY_SESSION_TYPES,
    _assign_quality_days,
    _DaySlot,
    _pick_quality_slot,
    _quality_quota,
)

from .conftest import OWNER_SPORTS, OwnerWeek


def _quality(sessions: list[dict[str, Any]], sport: str | None = None) -> list[dict[str, Any]]:
    return [
        s
        for s in sessions
        if s["session_type"] in _QUALITY_SESSION_TYPES and (sport is None or s["sport"] == sport)
    ]


def test_build_week_has_one_quality_session_per_race_discipline(owner_week: OwnerWeek) -> None:
    sessions = owner_week("build")
    for sport in OWNER_SPORTS:
        if not [s for s in sessions if s["sport"] == sport]:
            continue
        assert _quality(sessions, sport), f"aucune séance de qualité en {sport}"


def test_peak_week_still_carries_quality_for_every_discipline(owner_week: OwnerWeek) -> None:
    sessions = owner_week("peak")
    for sport in OWNER_SPORTS:
        if [s for s in sessions if s["sport"] == sport]:
            assert _quality(sessions, sport), f"peak sans qualité en {sport}"


def test_build_week_intensity_share_is_measurable(owner_week: OwnerWeek) -> None:
    sessions = owner_week("build")
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert training
    share = len(_quality(sessions)) / len(training)
    assert 0.2 <= share <= 0.6, f"répartition intensité/endurance hors norme ({share:.0%})"


def test_endurance_remains_the_backbone_of_the_week(owner_week: OwnerWeek) -> None:
    """La qualité ne doit pas dévorer la semaine : l'endurance reste majoritaire
    en volume horaire."""
    sessions = owner_week("build")
    quality_s = sum(s["target_duration_s"] for s in _quality(sessions))
    total_s = sum(
        s["target_duration_s"] for s in sessions if s["session_type"] not in ("rest", "race")
    )
    assert quality_s / total_s < 0.5


def test_no_two_hard_sessions_on_consecutive_days(owner_week: OwnerWeek) -> None:
    sessions = owner_week("build")
    hard_days = sorted(
        date.fromisoformat(s["date"]).weekday()
        for s in sessions
        if s["session_type"] in {"threshold", "pma", "sprint", "intervals"}
    )
    for previous, following in pairwise(hard_days):
        assert following - previous > 1, "deux séances dures consécutives"


def test_a_sport_without_any_session_gets_no_quality_quota() -> None:
    assert _quality_quota(level=1, phase="build", sessions=0) == 0


def test_a_single_session_sport_still_gets_exactly_one_quality_slot() -> None:
    assert _quality_quota(level=1, phase="build", sessions=1) == 1


def test_no_quality_slot_when_the_only_day_is_the_long_session_day() -> None:
    slots = [_DaySlot(offset=5, weekday=5, sport="run")]
    assert _pick_quality_slot(slots, {}, 5) is None


def test_a_sport_whose_only_day_is_the_long_day_claims_nothing() -> None:
    """Garde-fou : la sortie longue EST la séance du jour, on ne la remplace pas."""
    claimed = _assign_quality_days(
        slots=[_DaySlot(offset=5, weekday=5, sport="run")],
        types_by_sport={"run": ["endurance", "threshold", "long", "strides"]},
        strengths={"run": 3},
        phase="build",
        long_day_idx=5,
    )
    assert claimed == {}


def test_a_strong_athlete_gets_structured_intensity_not_only_strides(
    owner_week: OwnerWeek,
) -> None:
    sessions = owner_week("build", strengths={"swim": 4, "bike": 4, "run": 4})
    types = {s["session_type"] for s in _quality(sessions)}
    assert types & {"threshold", "pma", "sprint"}, "un niveau 4 doit dépasser les côtes courtes"
