"""Recent activity review used by coach recommendations.

The goal is not to summarize Garmin data. It is to extract a few coach-like
signals that should influence today's recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

InsightSeverity = Literal["positive", "watch", "risk"]


@dataclass(frozen=True)
class ActivityInsight:
    """One actionable coach observation from recent activities."""

    name: str
    severity: InsightSeverity
    message: str
    readiness_impact: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
            "readiness_impact": self.readiness_impact,
        }


@dataclass(frozen=True)
class ActivityReview:
    """Compact review of the athlete's recent training history."""

    lookback_days: int
    activities_7d: int
    activities_28d: int
    tss_7d: float
    avg_weekly_tss_prev_21d: float
    elevation_gain_7d: int
    avg_weekly_elevation_prev_21d: int
    sport_counts_28d: dict[str, int]
    days_since_last_activity: int | None
    insights: list[ActivityInsight]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lookback_days": self.lookback_days,
            "activities_7d": self.activities_7d,
            "activities_28d": self.activities_28d,
            "tss_7d": round(self.tss_7d, 1),
            "avg_weekly_tss_prev_21d": round(self.avg_weekly_tss_prev_21d, 1),
            "elevation_gain_7d": self.elevation_gain_7d,
            "avg_weekly_elevation_prev_21d": self.avg_weekly_elevation_prev_21d,
            "sport_counts_28d": self.sport_counts_28d,
            "days_since_last_activity": self.days_since_last_activity,
            "insights": [i.to_dict() for i in self.insights],
        }


def _activity_date(row: dict[str, Any]) -> date | None:
    raw = row.get("start_time")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _activity_tss(row: dict[str, Any]) -> float:
    raw_tss = row.get("tss")
    if raw_tss is not None:
        return float(raw_tss)
    duration_s = row.get("duration_s") or 0
    return max(0.0, float(duration_s) / 3600 * 50)


def _is_hard(row: dict[str, Any]) -> bool:
    duration_s = row.get("duration_s") or 0
    if duration_s <= 0:
        return False
    tss_per_hour = _activity_tss(row) / (float(duration_s) / 3600)
    return tss_per_hour >= 75


def _is_long_or_heavy(row: dict[str, Any]) -> bool:
    sport = str(row.get("sport") or "")
    duration_s = int(row.get("duration_s") or 0)
    tss = _activity_tss(row)
    if tss >= 100:
        return True
    if sport in {"bike", "cycling", "indoor_cycling", "mountain_biking"}:
        return duration_s >= 2 * 3600
    if sport in {"run", "running", "trail_running"}:
        return duration_s >= 75 * 60
    return duration_s >= 90 * 60


def _sum_tss(rows: list[dict[str, Any]]) -> float:
    return sum(_activity_tss(r) for r in rows)


def _sum_elevation(rows: list[dict[str, Any]]) -> int:
    return round(sum(float(r.get("elevation_gain_m") or 0) for r in rows))


def _sport_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        sport = str(row.get("sport") or "unknown")
        counts[sport] = counts.get(sport, 0) + 1
    return counts


def _recency_insight(
    *, activities_7d: list[dict[str, Any]], days_since_last_activity: int | None
) -> ActivityInsight | None:
    if days_since_last_activity is None:
        return ActivityInsight(
            "no_activity_history",
            "watch",
            "Pas encore assez d'historique : reste prudent sur l'intensité.",
        )
    if days_since_last_activity >= 10:
        return ActivityInsight(
            "return_after_break",
            "risk",
            f"Dernière activité il y a {days_since_last_activity} jours : reprise progressive.",
            -10,
        )
    if len(activities_7d) == 0:
        return ActivityInsight(
            "no_recent_activity",
            "watch",
            "Aucune activité sur 7 jours : évite de compenser avec une séance trop dure.",
        )
    return None


def _load_trend_insight(*, tss_7d: float, avg_weekly_tss_prev_21d: float) -> ActivityInsight | None:
    if avg_weekly_tss_prev_21d < 80:
        return None

    ratio = tss_7d / avg_weekly_tss_prev_21d
    if ratio >= 1.4 and tss_7d >= 140:
        return ActivityInsight(
            "load_spike",
            "risk",
            "Charge des 7 derniers jours nettement au-dessus de ta tendance.",
            -10,
        )
    if ratio <= 0.6:
        return ActivityInsight(
            "load_drop",
            "watch",
            "Charge récente en baisse : reprends sans chercher à rattraper.",
        )
    return None


def _hard_sessions_insight(activities_7d: list[dict[str, Any]]) -> ActivityInsight | None:
    hard_7d = [r for r in activities_7d if _is_hard(r)]
    if len(hard_7d) < 3:
        return None
    return ActivityInsight(
        "hard_sessions_density",
        "risk",
        "Plusieurs séances intenses récentes : privilégie récupération ou endurance facile.",
        -10,
    )


def _recent_long_insight(
    *, activities_7d: list[dict[str, Any]], today: date
) -> ActivityInsight | None:
    recent_long = [
        r
        for r in activities_7d
        if _is_long_or_heavy(r) and (d := _activity_date(r)) is not None and (today - d).days <= 2
    ]
    if not recent_long:
        return None
    return ActivityInsight(
        "recent_long_session",
        "watch",
        "Grosse séance récente : garde de la marge aujourd'hui.",
        -5,
    )


def _elevation_insight(
    *, elevation_7d: int, avg_weekly_elevation_prev_21d: int
) -> ActivityInsight | None:
    if avg_weekly_elevation_prev_21d < 200:
        return None

    elevation_ratio = elevation_7d / avg_weekly_elevation_prev_21d
    if elevation_ratio < 1.5 or elevation_7d < 500:
        return None
    return ActivityInsight(
        "elevation_spike",
        "watch",
        "Dénivelé récent élevé : attention à la fatigue musculaire.",
        -5,
    )


def _consistent_week_insight(
    *, activities_7d: list[dict[str, Any]], insights: list[ActivityInsight]
) -> ActivityInsight | None:
    if len(activities_7d) < 4 or any(i.severity == "risk" for i in insights):
        return None
    return ActivityInsight(
        "consistent_week",
        "positive",
        "Bonne régularité cette semaine : on peut construire sans forcer.",
        5,
    )


def _sport_imbalance_insight(activities_28d: list[dict[str, Any]]) -> ActivityInsight | None:
    counts = _sport_counts(activities_28d)
    total_28d = sum(counts.values())
    if total_28d < 6 or not counts:
        return None

    main_sport, main_count = max(counts.items(), key=lambda kv: kv[1])
    if main_count / total_28d < 0.8:
        return None
    return ActivityInsight(
        "sport_imbalance",
        "watch",
        f"Beaucoup de {main_sport} récemment : surveille l'équilibre entre disciplines.",
    )


def _append_if_present(insights: list[ActivityInsight], insight: ActivityInsight | None) -> None:
    if insight is not None:
        insights.append(insight)


def _build_insights(
    *,
    activities_7d: list[dict[str, Any]],
    activities_28d: list[dict[str, Any]],
    tss_7d: float,
    avg_weekly_tss_prev_21d: float,
    elevation_7d: int,
    avg_weekly_elevation_prev_21d: int,
    days_since_last_activity: int | None,
    today: date,
) -> list[ActivityInsight]:
    insights: list[ActivityInsight] = []

    _append_if_present(
        insights,
        _recency_insight(
            activities_7d=activities_7d,
            days_since_last_activity=days_since_last_activity,
        ),
    )
    _append_if_present(
        insights,
        _load_trend_insight(
            tss_7d=tss_7d,
            avg_weekly_tss_prev_21d=avg_weekly_tss_prev_21d,
        ),
    )
    _append_if_present(insights, _hard_sessions_insight(activities_7d))
    _append_if_present(insights, _recent_long_insight(activities_7d=activities_7d, today=today))
    _append_if_present(
        insights,
        _elevation_insight(
            elevation_7d=elevation_7d,
            avg_weekly_elevation_prev_21d=avg_weekly_elevation_prev_21d,
        ),
    )
    _append_if_present(
        insights,
        _consistent_week_insight(activities_7d=activities_7d, insights=insights),
    )
    _append_if_present(insights, _sport_imbalance_insight(activities_28d))

    return insights[:5]


def build_activity_review(
    activities: list[dict[str, Any]], today: date | None = None
) -> ActivityReview:
    """Build a coach-like review from activity rows ordered any way."""
    today = today or date.today()
    lookback_days = 90
    start_90d = today - timedelta(days=lookback_days)
    start_28d = today - timedelta(days=28)
    start_7d = today - timedelta(days=7)

    dated = [(d, row) for row in activities if (d := _activity_date(row)) is not None]
    in_90d = [(d, row) for d, row in dated if start_90d <= d <= today]
    rows_28d = [row for d, row in in_90d if d >= start_28d]
    rows_7d = [row for d, row in in_90d if d >= start_7d]
    rows_prev_21d = [row for d, row in in_90d if start_28d <= d < start_7d]

    tss_7d = _sum_tss(rows_7d)
    avg_weekly_tss_prev_21d = _sum_tss(rows_prev_21d) / 3
    elevation_7d = _sum_elevation(rows_7d)
    avg_weekly_elevation_prev_21d = round(_sum_elevation(rows_prev_21d) / 3)
    last_date = max((d for d, _row in in_90d), default=None)
    days_since_last_activity = (today - last_date).days if last_date else None

    insights = _build_insights(
        activities_7d=rows_7d,
        activities_28d=rows_28d,
        tss_7d=tss_7d,
        avg_weekly_tss_prev_21d=avg_weekly_tss_prev_21d,
        elevation_7d=elevation_7d,
        avg_weekly_elevation_prev_21d=avg_weekly_elevation_prev_21d,
        days_since_last_activity=days_since_last_activity,
        today=today,
    )

    return ActivityReview(
        lookback_days=lookback_days,
        activities_7d=len(rows_7d),
        activities_28d=len(rows_28d),
        tss_7d=round(tss_7d, 1),
        avg_weekly_tss_prev_21d=round(avg_weekly_tss_prev_21d, 1),
        elevation_gain_7d=elevation_7d,
        avg_weekly_elevation_prev_21d=avg_weekly_elevation_prev_21d,
        sport_counts_28d=_sport_counts(rows_28d),
        days_since_last_activity=days_since_last_activity,
        insights=insights,
    )
