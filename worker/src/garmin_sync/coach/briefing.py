"""Daily readiness briefing: scores HRV/sleep/TSB/etc and suggests adapted session.

Pure rule-based. No LLM. Inputs come from existing E2/E4/E7 tables (hrv, sleep,
daily_metrics, daily_banister_state, planned_sessions).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast

from garmin_sync.coach.activity_review import ActivityReview, build_activity_review
from garmin_sync.coach.session_feedback import SessionFeedback, activity_day, build_session_feedback
from garmin_sync.supabase_client import get_admin_client

Status = Literal["ready", "caution", "rest_advised"]
RecommendationAction = Literal["maintain", "ease", "rest", "caution"]
PlanAdjustmentAction = Literal["maintain", "ease", "replace_with_recovery", "protect_rest"]
PlanAdjustmentStatus = Literal["none", "suggested"]

# Reused by the per-table loaders below to type-narrow the Supabase response.
type _RowT = dict[str, Any] | None

# Score thresholds
READY_MIN = 70
CAUTION_MIN = 40
BASELINE_SCORE = 80
BRIEFING_CACHE_VERSION = "daily-briefing:v3"

log = logging.getLogger(__name__)

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
class CoachRecommendation:
    """Human-readable coach decision for today."""

    action: RecommendationAction
    title: str
    rationale: str
    instruction: str

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "title": self.title,
            "rationale": self.rationale,
            "instruction": self.instruction,
        }


@dataclass(frozen=True)
class NextSessionAdjustment:
    """Visible plan adjustment suggestion before any plan mutation."""

    status: PlanAdjustmentStatus
    action: PlanAdjustmentAction
    title: str
    rationale: str
    instruction: str
    target_session: dict[str, Any] | None
    suggested_session_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "title": self.title,
            "rationale": self.rationale,
            "instruction": self.instruction,
            "target_session": self.target_session,
            "suggested_session_type": self.suggested_session_type,
        }


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
    last_session_feedback: SessionFeedback | None
    coach_recommendation: CoachRecommendation
    next_session_adjustment: NextSessionAdjustment

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
            "last_session_feedback": (
                self.last_session_feedback.to_dict() if self.last_session_feedback else None
            ),
            "coach_recommendation": self.coach_recommendation.to_dict(),
            "next_session_adjustment": self.next_session_adjustment.to_dict(),
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


def build_coach_recommendation(
    *,
    status: Status,
    planned_session: dict[str, Any] | None,
    suggested_session: SuggestedSession | None,
    activity_review: ActivityReview,
    session_feedback: SessionFeedback | None,
) -> CoachRecommendation:
    """Translate signals into a clear coach decision for the athlete."""
    planned_type = str((planned_session or {}).get("session_type") or "séance")
    risk_insights = [i for i in activity_review.insights if i.severity == "risk"]

    if status == "rest_advised":
        return CoachRecommendation(
            action="rest",
            title="Repos ou récupération très facile",
            rationale="Les signaux de fatigue sont trop marqués pour empiler de la charge.",
            instruction="Garde au maximum 20-40 min en Z1 si tu veux bouger, sinon repos complet.",
        )

    if suggested_session:
        return CoachRecommendation(
            action="ease",
            title="Séance allégée",
            rationale=suggested_session.note,
            instruction=(
                "Reste sous contrôle : aisance respiratoire, pas de bloc au-dessus du seuil."
            ),
        )

    if session_feedback and session_feedback.severity == "risk":
        return CoachRecommendation(
            action="caution",
            title="Prudence sur la prochaine séance",
            rationale=session_feedback.message,
            instruction=(
                "Ne compense pas : garde la séance du jour facile ou raccourcis-la si besoin."
            ),
        )

    if risk_insights:
        return CoachRecommendation(
            action="caution",
            title="Séance maintenue avec marge",
            rationale=risk_insights[0].message,
            instruction=(
                "Exécute la séance sans chercher un record : "
                "RPE stable et récupération prioritaire."
            ),
        )

    return CoachRecommendation(
        action="maintain",
        title="Séance maintenue",
        rationale=f"Les signaux sont compatibles avec la séance {planned_type}.",
        instruction="Respecte les zones prévues et termine avec la sensation d'en garder un peu.",
    )


def _hard_session(session: dict[str, Any] | None) -> bool:
    if not session:
        return False
    return str(session.get("session_type") or "") in {"threshold", "intervals", "long", "race"}


def _hard_session_guardrail_factors(
    planned_session: dict[str, Any] | None,
    factors: list[ReadinessFactor],
) -> list[ReadinessFactor]:
    """Add a coach guardrail when a hard session meets unfavorable recovery signals."""
    if not _hard_session(planned_session):
        return []
    if str((planned_session or {}).get("session_type") or "") == "race":
        return []

    unfavorable = [
        factor
        for factor in factors
        if factor.impact <= -8
        and factor.name.startswith(
            (
                "hrv_",
                "sleep_",
                "tsb_",
                "body_battery_",
                "activity_",
                "session_feedback_",
            )
        )
    ]
    if not unfavorable:
        return []

    return [
        ReadinessFactor(
            "hard_session_guardrail",
            -10,
            "Séance dure prévue alors qu'un signal de récupération est défavorable.",
        )
    ]


def _adjustment_from_readiness_suggestion(
    planned_session: dict[str, Any],
    suggested_session: SuggestedSession | None,
) -> NextSessionAdjustment | None:
    if not suggested_session:
        return None
    action: PlanAdjustmentAction = (
        "protect_rest" if suggested_session.session_type == "rest" else "ease"
    )
    return NextSessionAdjustment(
        status="suggested",
        action=action,
        title="Ajustement proposé avant modification du plan",
        rationale=suggested_session.note,
        instruction="Valide l'adaptation seulement si les sensations confirment la fatigue.",
        target_session=planned_session,
        suggested_session_type=suggested_session.session_type,
    )


def _adjustment_from_session_feedback(
    planned_session: dict[str, Any],
    planned_type: str,
    session_feedback: SessionFeedback | None,
) -> NextSessionAdjustment | None:
    if not session_feedback or session_feedback.severity != "risk":
        return None
    if planned_type == "rest":
        return NextSessionAdjustment(
            status="suggested",
            action="protect_rest",
            title="Repos à protéger",
            rationale=session_feedback.message,
            instruction=(
                "Ne compense pas l'activité précédente : garde ce repos comme une séance utile."
            ),
            target_session=planned_session,
            suggested_session_type="rest",
        )
    if not _hard_session(planned_session):
        return None
    return NextSessionAdjustment(
        status="suggested",
        action="replace_with_recovery",
        title="Remplacer la séance dure",
        rationale=session_feedback.message,
        instruction=(
            "Passe en endurance facile ou récupération active, puis reprends le plan ensuite."
        ),
        target_session=planned_session,
        suggested_session_type="recovery",
    )


def _ease_hard_session_adjustment(
    *,
    planned_session: dict[str, Any],
    planned_type: str,
    rationale: str,
) -> NextSessionAdjustment:
    return NextSessionAdjustment(
        status="suggested",
        action="ease",
        title="Réduire l'intention de séance",
        rationale=rationale,
        instruction="Garde la séance, mais baisse l'intensité cible et conserve une marge cardio.",
        target_session=planned_session,
        suggested_session_type=_DOWNGRADE_ONE_LEVEL.get(planned_type, planned_type),
    )


def _adjustment_from_recent_signals(
    planned_session: dict[str, Any],
    planned_type: str,
    activity_review: ActivityReview,
    session_feedback: SessionFeedback | None,
) -> NextSessionAdjustment | None:
    if not _hard_session(planned_session):
        return None
    risk_insight = next((i for i in activity_review.insights if i.severity == "risk"), None)
    if risk_insight:
        return _ease_hard_session_adjustment(
            planned_session=planned_session,
            planned_type=planned_type,
            rationale=risk_insight.message,
        )
    if session_feedback and session_feedback.severity == "watch":
        return _ease_hard_session_adjustment(
            planned_session=planned_session,
            planned_type=planned_type,
            rationale=session_feedback.message,
        )
    return None


def build_next_session_adjustment(
    *,
    planned_session: dict[str, Any] | None,
    suggested_session: SuggestedSession | None,
    activity_review: ActivityReview,
    session_feedback: SessionFeedback | None,
) -> NextSessionAdjustment:
    """Suggest how to adapt today's planned session before changing the plan."""
    if not planned_session:
        return NextSessionAdjustment(
            status="none",
            action="maintain",
            title="Pas d'ajustement de plan",
            rationale="Aucune séance planifiée à ajuster aujourd'hui.",
            instruction="Garde les recommandations générales du coach.",
            target_session=None,
        )

    planned_type = str(planned_session.get("session_type") or "unknown")

    for adjustment in (
        _adjustment_from_readiness_suggestion(planned_session, suggested_session),
        _adjustment_from_session_feedback(planned_session, planned_type, session_feedback),
        _adjustment_from_recent_signals(
            planned_session, planned_type, activity_review, session_feedback
        ),
    ):
        if adjustment:
            return adjustment

    return NextSessionAdjustment(
        status="none",
        action="maintain",
        title="Plan maintenu",
        rationale="Aucun signal ne justifie de modifier la séance du jour.",
        instruction="Suis la séance prévue et surveille les sensations.",
        target_session=planned_session,
    )


def _no_repeated_adjustment(planned_session: dict[str, Any] | None) -> NextSessionAdjustment:
    return NextSessionAdjustment(
        status="none",
        action="maintain",
        title="Ajustement déjà traité",
        rationale="Cette proposition a déjà été acceptée ou ignorée.",
        instruction="Le coach ne repropose pas le même ajustement pour cette séance.",
        target_session=planned_session,
    )


def _load_adjustment_decision(
    db: Any,
    user_id: str,
    adjustment: NextSessionAdjustment,
) -> dict[str, Any] | None:
    target_id = (adjustment.target_session or {}).get("id")
    suggested_type = adjustment.suggested_session_type
    if adjustment.status != "suggested" or not target_id or not suggested_type:
        return None
    resp = (
        db.table("coach_adjustment_decisions")
        .select("decision")
        .eq("user_id", user_id)
        .eq("planned_session_id", str(target_id))
        .eq("suggested_session_type", suggested_type)
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


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
        .order("start_time", desc=True)
        .execute()
    )
    return cast("list[dict[str, Any]]", resp.data or [])


def _load_planned_session_for_date(
    db: Any, user_id: str, session_date: date
) -> dict[str, Any] | None:
    resp = (
        db.table("planned_sessions")
        .select(
            "id, date, sport, session_type, target_duration_s, target_tss, "
            "target_elevation_gain_m, phase"
        )
        .eq("user_id", user_id)
        .eq("date", session_date.isoformat())
        .maybe_single()
        .execute()
    )
    return cast(_RowT, resp.data if resp else None)


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


def _session_feedback_factor(feedback: SessionFeedback | None) -> list[ReadinessFactor]:
    if not feedback or feedback.readiness_impact == 0:
        return []
    return [
        ReadinessFactor(
            f"session_feedback_{feedback.verdict}",
            feedback.readiness_impact,
            feedback.message,
        )
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
    recent_activities = _load_recent_activities(db, user_id, today)
    activity_review = build_activity_review(recent_activities, today)
    latest_activity = recent_activities[0] if recent_activities else None
    latest_activity_date = activity_day(latest_activity) if latest_activity else None
    feedback_planned = (
        _load_planned_session_for_date(db, user_id, latest_activity_date)
        if latest_activity_date
        else None
    )
    session_feedback = build_session_feedback(
        activity=latest_activity,
        planned_session=feedback_planned,
    )

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
    factors.extend(_session_feedback_factor(session_feedback))
    factors.extend(_hard_session_guardrail_factors(planned, factors))

    score = BASELINE_SCORE + sum(f.impact for f in factors)
    score = max(0, min(100, score))

    status = derive_status(score)
    suggestion = suggest_adjustment(planned, status)
    coach_recommendation = build_coach_recommendation(
        status=status,
        planned_session=planned,
        suggested_session=suggestion,
        activity_review=activity_review,
        session_feedback=session_feedback,
    )
    next_session_adjustment = build_next_session_adjustment(
        planned_session=planned,
        suggested_session=suggestion,
        activity_review=activity_review,
        session_feedback=session_feedback,
    )
    if _load_adjustment_decision(db, user_id, next_session_adjustment):
        next_session_adjustment = _no_repeated_adjustment(planned)
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
        last_session_feedback=session_feedback,
        coach_recommendation=coach_recommendation,
        next_session_adjustment=next_session_adjustment,
    )


def get_cached_daily_briefing(user_id: str, today: date | None = None) -> dict[str, Any] | None:
    """Return today's cached briefing payload when it matches the coach logic version."""
    briefing_date = today or date.today()
    db = get_admin_client()
    try:
        resp = (
            db.table("coach_daily_briefings")
            .select("payload, logic_version")
            .eq("user_id", user_id)
            .eq("briefing_date", briefing_date.isoformat())
            .maybe_single()
            .execute()
        )
    except Exception:
        log.warning("daily briefing cache read failed for user=%s", user_id, exc_info=True)
        return None

    row = cast(dict[str, Any] | None, resp.data if resp else None)
    if not row or row.get("logic_version") != BRIEFING_CACHE_VERSION:
        return None
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else None


def compute_and_cache_daily_briefing(
    user_id: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Compute today's briefing, store it for fast subsequent /today loads, and return it."""
    briefing_date = today or date.today()
    payload = compute_briefing(user_id=user_id, today=briefing_date).to_dict()
    db = get_admin_client()
    try:
        db.table("coach_daily_briefings").upsert(
            {
                "user_id": user_id,
                "briefing_date": briefing_date.isoformat(),
                "logic_version": BRIEFING_CACHE_VERSION,
                "payload": payload,
                "computed_at": datetime.now(UTC).isoformat(),
            },
            on_conflict="user_id,briefing_date",
        ).execute()
    except Exception:
        log.warning("daily briefing cache write failed for user=%s", user_id, exc_info=True)
    return payload
