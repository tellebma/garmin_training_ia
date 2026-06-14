"""Daily readiness briefing: scores HRV/sleep/TSB/etc and suggests adapted session.

Pure rule-based. No LLM. Inputs come from existing E2/E4/E7 tables (hrv, sleep,
daily_metrics, daily_banister_state, planned_sessions).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.supabase_client import get_admin_client

Status = Literal["ready", "caution", "rest_advised"]

# Reused by the per-table loaders below to type-narrow the Supabase response.
type _RowT = dict[str, Any] | None

# Score thresholds
READY_MIN = 70
CAUTION_MIN = 40
BASELINE_SCORE = 80

# Session downgrade map: each session type maps to its one-step-lighter version.
# Race is intentionally not in the map — race day overrides everything.
_DOWNGRADE_ONE_LEVEL: dict[str, str] = {
    "intervals": "threshold",
    "threshold": "endurance",
    "long": "endurance",
    "endurance": "recovery",
    "recovery": "rest",
    "rest": "rest",
}


@dataclass(frozen=True)
class ReadinessFactor:
    """A single signal contributing to the readiness score."""

    name: str
    impact: int  # signed: negative = penalty, positive = bonus
    explanation: str


@dataclass(frozen=True)
class SuggestedSession:
    """Adapted session proposal when status != ready."""

    sport: str
    session_type: str
    note: str


@dataclass(frozen=True)
class DailyBriefing:
    """Full briefing payload returned by /coach/daily-briefing."""

    date: str
    readiness_score: int
    status: Status
    explanation_md: str
    factors: list[ReadinessFactor]
    planned_session: dict[str, Any] | None
    suggested_session: SuggestedSession | None
    activity_review: ActivityReview

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "readiness_score": self.readiness_score,
            "status": self.status,
            "explanation_md": self.explanation_md,
            "factors": [
                {"name": f.name, "impact": f.impact, "explanation": f.explanation}
                for f in self.factors
            ],
            "planned_session": self.planned_session,
            "suggested_session": (
                {
                    "sport": self.suggested_session.sport,
                    "session_type": self.suggested_session.session_type,
                    "note": self.suggested_session.note,
                }
                if self.suggested_session
                else None
            ),
            "activity_review": self.activity_review.to_dict(),
        }


def _score_hrv(today_hrv: dict[str, Any] | None, weekly_avg: float | None) -> list[ReadinessFactor]:
    """Score HRV signal. Lower = penalty."""
    if not today_hrv:
        return [ReadinessFactor("hrv_missing", 0, "Pas de HRV mesurée aujourd'hui.")]

    factors: list[ReadinessFactor] = []
    rmssd = today_hrv.get("hrv_rmssd")
    status = today_hrv.get("hrv_status")

    if rmssd is not None and weekly_avg and weekly_avg > 0:
        ratio = float(rmssd) / weekly_avg
        if ratio < 0.70:
            factors.append(
                ReadinessFactor(
                    "hrv_very_low",
                    -25,
                    f"HRV très basse ({rmssd:.0f} vs moyenne {weekly_avg:.0f}).",
                )
            )
        elif ratio < 0.85:
            factors.append(
                ReadinessFactor(
                    "hrv_low",
                    -10,
                    f"HRV un peu basse ({rmssd:.0f} vs moyenne {weekly_avg:.0f}).",
                )
            )
        elif ratio > 1.10:
            factors.append(ReadinessFactor("hrv_high", 5, "HRV au-dessus de la moyenne."))

    if status in {"unbalanced", "poor", "low"}:
        factors.append(ReadinessFactor("hrv_status_bad", -15, f"État HRV : {status}."))

    return factors


def _score_sleep(sleep_row: dict[str, Any] | None) -> list[ReadinessFactor]:
    if not sleep_row:
        return [ReadinessFactor("sleep_missing", 0, "Pas de données de sommeil hier.")]

    factors: list[ReadinessFactor] = []
    duration_s = sleep_row.get("sleep_duration_s") or 0
    score = sleep_row.get("sleep_score") or 0
    hours = duration_s / 3600

    if 0 < hours < 6:
        factors.append(ReadinessFactor("sleep_very_short", -15, f"Sommeil court ({hours:.1f}h)."))
    elif 6 <= hours < 7:
        factors.append(ReadinessFactor("sleep_short", -5, f"Sommeil léger ({hours:.1f}h)."))

    if 0 < score < 50:
        factors.append(ReadinessFactor("sleep_low_score", -10, f"Score sommeil bas ({score})."))

    if hours >= 8 and score >= 80:
        factors.append(ReadinessFactor("sleep_excellent", 5, "Excellent sommeil."))

    return factors


def _score_resting_hr(
    daily: dict[str, Any] | None, baseline: float | None
) -> list[ReadinessFactor]:
    if not daily or not baseline or baseline <= 0:
        return []
    resting = daily.get("resting_hr")
    if not resting:
        return []
    if resting > baseline * 1.10:
        return [
            ReadinessFactor(
                "resting_hr_high",
                -10,
                f"FC repos élevée ({resting} vs ligne {baseline:.0f}).",
            )
        ]
    return []


def _score_tsb(tsb: float | None) -> list[ReadinessFactor]:
    if tsb is None:
        return []
    if tsb < -30:
        return [ReadinessFactor("tsb_very_negative", -15, f"TSB très négatif ({tsb:.0f}).")]
    if tsb < -20:
        return [ReadinessFactor("tsb_negative", -8, f"TSB négatif ({tsb:.0f}).")]
    if tsb > 5:
        return [ReadinessFactor("tsb_fresh", 5, f"TSB positif ({tsb:.0f}) : tu es frais.")]
    return []


def _score_body_battery(daily: dict[str, Any] | None) -> list[ReadinessFactor]:
    if not daily:
        return []
    bb = daily.get("body_battery_low")
    if bb is not None and bb < 30:
        return [ReadinessFactor("body_battery_low", -10, f"Body Battery bas hier soir ({bb}).")]
    return []


def derive_status(score: int) -> Status:
    if score >= READY_MIN:
        return "ready"
    if score >= CAUTION_MIN:
        return "caution"
    return "rest_advised"


def suggest_adjustment(
    planned_session: dict[str, Any] | None, status: Status
) -> SuggestedSession | None:
    """If status != ready, downgrade the planned session by one level."""
    if planned_session is None or status == "ready":
        return None
    sport = planned_session.get("sport", "rest")
    stype = planned_session.get("session_type", "rest")
    # Race day overrides: never downgrade
    if stype == "race":
        return None
    if status == "rest_advised":
        return SuggestedSession(
            sport="rest",
            session_type="rest",
            note="Repos conseillé : signes de fatigue marqués.",
        )
    # caution: downgrade one level
    new_type = _DOWNGRADE_ONE_LEVEL.get(stype, stype)
    if new_type == stype:
        return None
    return SuggestedSession(
        sport=sport, session_type=new_type, note=f"Allégé : {stype} -> {new_type}."
    )


def format_explanation_md(factors: list[ReadinessFactor], status: Status) -> str:
    """Build a short FR markdown explanation from the factors."""
    negatives = [f for f in factors if f.impact < 0]
    if not negatives:
        if status == "ready":
            return "Tous les signaux sont bons. Bonne séance !"
        return "Conditions correctes mais pas de données récentes pour affiner."
    head = {
        "ready": "Légers signaux à surveiller :",
        "caution": "Quelques signes de fatigue :",
        "rest_advised": "Signes de fatigue marqués :",
    }[status]
    bullets = "\n".join(f"- {f.explanation}" for f in negatives)
    return f"{head}\n\n{bullets}"


def _load_planned_session(db: Any, user_id: str, today: date) -> dict[str, Any] | None:
    resp = (
        db.table("planned_sessions")
        .select("id, date, sport, session_type, target_duration_s, target_tss, phase, workout")
        .eq("user_id", user_id)
        .eq("date", today.isoformat())
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


def _load_today_hrv(db: Any, user_id: str, today: date) -> dict[str, Any] | None:
    resp = (
        db.table("hrv")
        .select("hrv_rmssd, hrv_status, hrv_weekly_avg")
        .eq("user_id", user_id)
        .eq("date", today.isoformat())
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


def _load_recent_sleep(db: Any, user_id: str, today: date) -> dict[str, Any] | None:
    yesterday = today - timedelta(days=1)
    resp = (
        db.table("sleep")
        .select("sleep_duration_s, sleep_score")
        .eq("user_id", user_id)
        .eq("date", yesterday.isoformat())
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


def _load_daily_metrics(db: Any, user_id: str, today: date) -> dict[str, Any] | None:
    yesterday = today - timedelta(days=1)
    resp = (
        db.table("daily_metrics")
        .select("resting_hr, body_battery_low")
        .eq("user_id", user_id)
        .eq("date", yesterday.isoformat())
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


def _load_resting_hr_baseline(db: Any, user_id: str, today: date) -> float | None:
    """Median resting_hr over last 30 days."""
    start = today - timedelta(days=30)
    resp = (
        db.table("daily_metrics")
        .select("resting_hr")
        .eq("user_id", user_id)
        .gte("date", start.isoformat())
        .execute()
    )
    rows = cast("list[dict[str, Any]]", resp.data or [])
    values = [r["resting_hr"] for r in rows if r.get("resting_hr")]
    if not values:
        return None
    values.sort()
    return float(values[len(values) // 2])


def _load_tsb(db: Any, user_id: str, today: date) -> float | None:
    resp = (
        db.table("daily_banister_state")
        .select("tsb")
        .eq("user_id", user_id)
        .eq("date", today.isoformat())
        .maybe_single()
        .execute()
    )
    row = cast(_RowT, resp.data if resp else None)
    if not row:
        return None
    val = row.get("tsb")
    return float(val) if val is not None else None


def _load_recent_activities(db: Any, user_id: str, today: date) -> list[dict[str, Any]]:
    start = today - timedelta(days=90)
    resp = (
        db.table("activities")
        .select("start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg")
        .eq("user_id", user_id)
        .gte("start_time", start.isoformat())
        .execute()
    )
    return cast("list[dict[str, Any]]", resp.data or [])


def _activity_review_factors(review: ActivityReview) -> list[ReadinessFactor]:
    return [
        ReadinessFactor(
            f"activity_{insight.name}",
            insight.readiness_impact,
            insight.message,
        )
        for insight in review.insights
        if insight.readiness_impact != 0
    ]


def compute_briefing(user_id: str, today: date | None = None) -> DailyBriefing:
    """Compute the full daily briefing for one user. Single DB round-trip per source."""
    today = today or date.today()
    db = get_admin_client()

    hrv = _load_today_hrv(db, user_id, today)
    sleep_row = _load_recent_sleep(db, user_id, today)
    daily = _load_daily_metrics(db, user_id, today)
    rh_baseline = _load_resting_hr_baseline(db, user_id, today)
    tsb = _load_tsb(db, user_id, today)
    planned = _load_planned_session(db, user_id, today)
    activity_review = build_activity_review(_load_recent_activities(db, user_id, today), today)

    weekly_avg = None
    if hrv and hrv.get("hrv_weekly_avg"):
        weekly_avg = float(hrv["hrv_weekly_avg"])

    factors: list[ReadinessFactor] = []
    factors.extend(_score_hrv(hrv, weekly_avg))
    factors.extend(_score_sleep(sleep_row))
    factors.extend(_score_resting_hr(daily, rh_baseline))
    factors.extend(_score_tsb(tsb))
    factors.extend(_score_body_battery(daily))
    factors.extend(_activity_review_factors(activity_review))

    score = BASELINE_SCORE + sum(f.impact for f in factors)
    score = max(0, min(100, score))

    status = derive_status(score)
    suggestion = suggest_adjustment(planned, status)
    explanation = format_explanation_md(factors, status)

    return DailyBriefing(
        date=today.isoformat(),
        readiness_score=score,
        status=status,
        explanation_md=explanation,
        factors=factors,
        planned_session=planned,
        suggested_session=suggestion,
        activity_review=activity_review,
    )
