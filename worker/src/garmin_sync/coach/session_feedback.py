"""Post-session feedback comparing completed activity to the planned session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

FeedbackSeverity = Literal["positive", "watch", "risk"]

_EQUIVALENT_SPORTS: dict[str, set[str]] = {
    "bike": {"bike", "cycling", "indoor_cycling", "mountain_biking"},
    "run": {"run", "running", "trail_running", "treadmill_running"},
    "swim": {"swim", "swimming", "lap_swimming", "open_water_swimming"},
    "brick": {"brick", "multi_sport", "transition"},
}


@dataclass(frozen=True)
class SessionFeedback:
    """Coach feedback for one completed activity."""

    activity_date: str
    sport: str
    planned_sport: str | None
    planned_session_type: str | None
    verdict: str
    severity: FeedbackSeverity
    message: str
    readiness_impact: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_date": self.activity_date,
            "sport": self.sport,
            "planned_sport": self.planned_sport,
            "planned_session_type": self.planned_session_type,
            "verdict": self.verdict,
            "severity": self.severity,
            "message": self.message,
            "readiness_impact": self.readiness_impact,
        }


def activity_day(activity: dict[str, Any]) -> date | None:
    raw = activity.get("start_time")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _same_sport(activity_sport: str, planned_sport: str) -> bool:
    activity_norm = activity_sport.lower()
    planned_norm = planned_sport.lower()
    if activity_norm == planned_norm:
        return True
    equivalents = _EQUIVALENT_SPORTS.get(planned_norm, {planned_norm})
    return activity_norm in equivalents


def _ratio(actual: float | int | None, target: float | int | None) -> float | None:
    if actual is None or target is None or target <= 0:
        return None
    return float(actual) / float(target)


def _feedback(
    *,
    activity_date: date,
    sport: str,
    planned_sport: str | None,
    planned_type: str | None,
    verdict: str,
    severity: FeedbackSeverity,
    message: str,
    readiness_impact: int = 0,
) -> SessionFeedback:
    return SessionFeedback(
        activity_date=activity_date.isoformat(),
        sport=sport,
        planned_sport=planned_sport,
        planned_session_type=planned_type,
        verdict=verdict,
        severity=severity,
        message=message,
        readiness_impact=readiness_impact,
    )


def _unplanned_feedback(*, activity_date: date, sport: str) -> SessionFeedback:
    return _feedback(
        activity_date=activity_date,
        sport=sport,
        planned_sport=None,
        planned_type=None,
        verdict="unplanned",
        severity="watch",
        message="Activité réalisée hors plan : ne compense pas automatiquement demain.",
    )


def _rest_day_feedback(
    *, activity_date: date, sport: str, planned_sport: str, planned_type: str
) -> SessionFeedback:
    return _feedback(
        activity_date=activity_date,
        sport=sport,
        planned_sport=planned_sport,
        planned_type=planned_type,
        verdict="trained_on_rest_day",
        severity="risk",
        message="Tu t'es entraîné sur un jour de repos : garde la prochaine séance facile.",
        readiness_impact=-8,
    )


def _sport_mismatch_feedback(
    *, activity_date: date, sport: str, planned_sport: str, planned_type: str
) -> SessionFeedback:
    return _feedback(
        activity_date=activity_date,
        sport=sport,
        planned_sport=planned_sport,
        planned_type=planned_type,
        verdict="sport_mismatch",
        severity="watch",
        message=f"Activité {sport} réalisée au lieu de {planned_sport} : ajuste sans rattraper.",
        readiness_impact=-3,
    )


def _execution_feedback(
    *,
    activity: dict[str, Any],
    activity_date: date,
    sport: str,
    planned_sport: str,
    planned_type: str,
    planned_session: dict[str, Any],
) -> SessionFeedback:
    duration_ratio = _ratio(activity.get("duration_s"), planned_session.get("target_duration_s"))
    tss_ratio = _ratio(activity.get("tss"), planned_session.get("target_tss"))
    elevation_gain = activity.get("elevation_gain_m")
    elevation_ratio = _ratio(elevation_gain, planned_session.get("target_elevation_gain_m"))

    if tss_ratio is not None and tss_ratio >= 1.3:
        return _feedback(
            activity_date=activity_date,
            sport=sport,
            planned_sport=planned_sport,
            planned_type=planned_type,
            verdict="too_intense",
            severity="risk",
            message="Séance plus intense que prévu : évite d'empiler une autre séance dure.",
            readiness_impact=-10,
        )

    if duration_ratio is not None and duration_ratio >= 1.35:
        return _feedback(
            activity_date=activity_date,
            sport=sport,
            planned_sport=planned_sport,
            planned_type=planned_type,
            verdict="too_long",
            severity="watch",
            message="Séance plus longue que prévu : surveille la récupération avant la suite.",
            readiness_impact=-5,
        )

    if (
        duration_ratio is not None
        and duration_ratio <= 0.65
        and planned_type
        not in {
            "recovery",
            "rest",
        }
    ):
        return _feedback(
            activity_date=activity_date,
            sport=sport,
            planned_sport=planned_sport,
            planned_type=planned_type,
            verdict="too_short",
            severity="watch",
            message="Séance écourtée : on ne rattrape pas tout d'un coup, on reprend proprement.",
        )

    if elevation_ratio is not None and elevation_ratio >= 1.5 and elevation_gain:
        return _feedback(
            activity_date=activity_date,
            sport=sport,
            planned_sport=planned_sport,
            planned_type=planned_type,
            verdict="more_elevation",
            severity="watch",
            message="Dénivelé nettement supérieur au prévu : attention à la fatigue musculaire.",
            readiness_impact=-5,
        )

    return _feedback(
        activity_date=activity_date,
        sport=sport,
        planned_sport=planned_sport,
        planned_type=planned_type,
        verdict="well_executed",
        severity="positive",
        message="Séance bien exécutée : reste régulier, sans ajouter de charge inutile.",
        readiness_impact=3,
    )


def build_session_feedback(
    *,
    activity: dict[str, Any] | None,
    planned_session: dict[str, Any] | None,
) -> SessionFeedback | None:
    """Compare one completed activity with its planned session, if possible."""
    if not activity:
        return None

    day = activity_day(activity)
    if day is None:
        return None

    sport = str(activity.get("sport") or "unknown")

    if not planned_session:
        return _unplanned_feedback(activity_date=day, sport=sport)

    planned_sport = str(planned_session.get("sport") or "unknown")
    planned_type = str(planned_session.get("session_type") or "unknown")

    if planned_type == "rest" or planned_sport == "rest":
        return _rest_day_feedback(
            activity_date=day, sport=sport, planned_sport=planned_sport, planned_type=planned_type
        )

    if not _same_sport(sport, planned_sport):
        return _sport_mismatch_feedback(
            activity_date=day, sport=sport, planned_sport=planned_sport, planned_type=planned_type
        )

    return _execution_feedback(
        activity=activity,
        activity_date=day,
        sport=sport,
        planned_sport=planned_sport,
        planned_type=planned_type,
        planned_session=planned_session,
    )
