from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock, patch

from garmin_sync.coach.activity_review import ActivityInsight, build_activity_review
from garmin_sync.coach.briefing import (
    BASELINE_SCORE,
    BRIEFING_CACHE_VERSION,
    CoachRecommendation,
    DailyBriefing,
    NextSessionAdjustment,
    ReadinessFactor,
    SuggestedSession,
    _hard_session_guardrail_factors,
    _score_steps,
    build_coach_recommendation,
    build_next_session_adjustment,
    compute_and_cache_daily_briefing,
    compute_briefing,
    derive_status,
    format_explanation_md,
    get_cached_daily_briefing,
    suggest_adjustment,
)
from garmin_sync.coach.session_feedback import SessionFeedback


def test_derive_status_thresholds():
    assert derive_status(100) == "ready"
    assert derive_status(70) == "ready"
    assert derive_status(69) == "caution"
    assert derive_status(40) == "caution"
    assert derive_status(39) == "rest_advised"
    assert derive_status(0) == "rest_advised"


def test_suggest_adjustment_ready_keeps_session():
    planned = {"sport": "run", "session_type": "intervals"}
    assert suggest_adjustment(planned, "ready") is None


def test_suggest_adjustment_caution_downgrades_one_level():
    cases = [
        ("intervals", "threshold"),
        ("threshold", "endurance"),
        ("long", "endurance"),
        ("endurance", "recovery"),
        ("recovery", "rest"),
    ]
    for original, expected in cases:
        planned = {"sport": "bike", "session_type": original}
        s = suggest_adjustment(planned, "caution")
        assert s is not None, f"expected suggestion for {original}"
        assert s.session_type == expected


def test_suggest_adjustment_rest_advised_forces_rest():
    planned = {"sport": "run", "session_type": "intervals"}
    s = suggest_adjustment(planned, "rest_advised")
    assert s is not None
    assert s.sport == "rest"
    assert s.session_type == "rest"


def test_suggest_adjustment_race_day_never_downgrades():
    planned = {"sport": "run", "session_type": "race"}
    assert suggest_adjustment(planned, "caution") is None
    assert suggest_adjustment(planned, "rest_advised") is None


def test_suggest_adjustment_no_planned_returns_none():
    assert suggest_adjustment(None, "caution") is None


def test_hard_session_guardrail_requires_hard_non_race_session():
    factors = [ReadinessFactor("hrv_low", -10, "HRV un peu basse.")]

    assert _hard_session_guardrail_factors(None, factors) == []
    assert _hard_session_guardrail_factors({"session_type": "endurance"}, factors) == []
    assert _hard_session_guardrail_factors({"session_type": "race"}, factors) == []


def test_hard_session_guardrail_ignores_weak_or_unrelated_signals():
    planned = {"session_type": "intervals"}

    assert _hard_session_guardrail_factors(planned, []) == []
    assert (
        _hard_session_guardrail_factors(
            planned,
            [ReadinessFactor("sleep_short", -5, "Sommeil un peu court.")],
        )
        == []
    )
    assert (
        _hard_session_guardrail_factors(
            planned,
            [ReadinessFactor("resting_hr_high", -10, "FC repos élevée.")],
        )
        == []
    )


def test_hard_session_guardrail_adds_penalty_for_unfavorable_recovery_signal():
    factors = _hard_session_guardrail_factors(
        {"session_type": "threshold"},
        [ReadinessFactor("tsb_negative", -8, "TSB négatif.")],
    )

    assert factors == [
        ReadinessFactor(
            "hard_session_guardrail",
            -10,
            "Séance dure prévue alors qu'un signal de récupération est défavorable.",
        )
    ]


def test_hard_session_guardrail_adds_penalty_for_pma_session():
    factors = _hard_session_guardrail_factors(
        {"session_type": "pma"},
        [ReadinessFactor("tsb_negative", -8, "TSB négatif.")],
    )

    assert factors == [
        ReadinessFactor(
            "hard_session_guardrail",
            -10,
            "Séance dure prévue alors qu'un signal de récupération est défavorable.",
        )
    ]


def test_format_explanation_md_ready_no_negatives():
    md = format_explanation_md([], "ready")
    assert "Bonne" in md


def test_format_explanation_md_caution_lists_negatives():
    factors = [
        ReadinessFactor("hrv_low", -10, "HRV un peu basse."),
        ReadinessFactor("sleep_short", -5, "Sommeil court."),
    ]
    md = format_explanation_md(factors, "caution")
    assert "HRV un peu basse" in md
    assert "Sommeil court" in md
    assert "signes de fatigue" in md.lower()


def test_format_explanation_md_rest_day_no_negatives_avoids_bonne_seance():
    md = format_explanation_md([], "ready", is_rest_day=True)
    assert "Bonne séance" not in md
    assert "repos" in md.lower() or "récup" in md.lower()


def test_format_explanation_md_rest_day_keeps_fatigue_bullets():
    factors = [
        ReadinessFactor("hrv_low", -10, "HRV un peu basse."),
        ReadinessFactor("sleep_short", -5, "Sommeil court."),
    ]
    md = format_explanation_md(factors, "rest_advised", is_rest_day=True)
    assert "HRV un peu basse" in md
    assert "Sommeil court" in md
    assert "Bonne séance" not in md


def test_build_coach_recommendation_rest_advised_is_clear():
    rec = build_coach_recommendation(
        status="rest_advised",
        planned_session={"session_type": "intervals"},
        suggested_session=SuggestedSession("rest", "rest", "Repos conseillé."),
        activity_review=_empty_review(),
        session_feedback=None,
    )

    assert rec.action == "rest"
    assert "Repos" in rec.title
    assert "Z1" in rec.instruction


def _rest_review_with_risk_insight():
    review = _empty_review()
    return replace(
        review,
        insights=[
            ActivityInsight(
                "load_spike",
                "risk",
                "Charge des 7 derniers jours nettement au-dessus de ta tendance.",
                -10,
            )
        ],
    )


def test_build_coach_recommendation_rest_day_never_says_execute_the_session():
    """Regression #132: a rest day combined with a risk insight (e.g. load_spike, which is
    almost always present) must never produce an "execute the session" instruction — there
    is no session to execute.
    """
    rec = build_coach_recommendation(
        status="ready",
        planned_session={"sport": "rest", "session_type": "rest", "target_duration_s": 0},
        suggested_session=None,
        activity_review=_rest_review_with_risk_insight(),
        session_feedback=None,
    )

    assert "exécute la séance" not in rec.instruction.lower()
    assert rec.action == "rest"


def test_build_coach_recommendation_rest_day_without_risk_stays_a_rest_message():
    rec = build_coach_recommendation(
        status="ready",
        planned_session={"sport": "rest", "session_type": "rest", "target_duration_s": 0},
        suggested_session=None,
        activity_review=_empty_review(),
        session_feedback=None,
    )

    assert rec.action == "rest"
    assert "exécute la séance" not in rec.instruction.lower()
    assert "suis la séance prévue" not in rec.instruction.lower()


def _mock_db_with(
    *,
    hrv=None,
    sleep=None,
    daily=None,
    tsb=None,
    planned=None,
    adjustment_decision=None,
    baseline_rows=None,
    activities=None,
    recovery_baselines=None,
):
    """Build a MagicMock db that returns the given rows for each table query."""
    db = MagicMock()

    def _table_router(table_name: str):
        m = MagicMock()
        single = m.select.return_value.eq.return_value.eq.return_value.maybe_single
        if table_name == "hrv":
            single.return_value.execute.return_value.data = hrv
        elif table_name == "sleep":
            single.return_value.execute.return_value.data = sleep
        elif table_name == "daily_metrics":
            single.return_value.execute.return_value.data = daily
            range_q = m.select.return_value.eq.return_value.gte.return_value.execute.return_value
            range_q.data = baseline_rows or []
        elif table_name == "daily_banister_state":
            row = {"tsb": tsb} if tsb is not None else None
            single.return_value.execute.return_value.data = row
        elif table_name == "planned_sessions":
            single.return_value.execute.return_value.data = planned
        elif table_name == "coach_adjustment_decisions":
            decision_single = (
                m.select.return_value.eq.return_value.eq.return_value.eq.return_value.maybe_single
            )
            decision_single.return_value.execute.return_value.data = adjustment_decision
        elif table_name == "activities":
            activities_query = (
                m.select.return_value.eq.return_value.gte.return_value.order.return_value
            )
            rows_q = activities_query.execute.return_value
            rows_q.data = activities or []
        elif table_name == "recovery_baselines":
            rb_single = m.select.return_value.eq.return_value.maybe_single
            rb_single.return_value.execute.return_value.data = recovery_baselines
        return m

    db.table.side_effect = _table_router
    return db


def _empty_review():
    return build_activity_review([], today=date(2026, 5, 20))


def _no_next_adjustment() -> NextSessionAdjustment:
    return NextSessionAdjustment(
        status="none",
        action="maintain",
        title="Plan maintenu",
        rationale="ok",
        instruction="Suis la séance prévue.",
        target_session=None,
    )


def test_build_next_session_adjustment_uses_readiness_suggestion():
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "run", "session_type": "intervals"},
        suggested_session=SuggestedSession("run", "threshold", "Allégé : intervals -> threshold."),
        activity_review=_empty_review(),
        session_feedback=None,
    )

    assert adjustment.status == "suggested"
    assert adjustment.action == "ease"
    assert adjustment.suggested_session_type == "threshold"
    assert adjustment.target_session is not None


def test_build_next_session_adjustment_replaces_hard_session_after_risky_feedback():
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "run", "session_type": "intervals"},
        suggested_session=None,
        activity_review=_empty_review(),
        session_feedback=build_session_feedback_for_test(severity="risk"),
    )

    assert adjustment.status == "suggested"
    assert adjustment.action == "replace_with_recovery"
    assert adjustment.suggested_session_type == "recovery"


def test_build_next_session_adjustment_protects_rest_after_risky_feedback():
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "rest", "session_type": "rest"},
        suggested_session=None,
        activity_review=_empty_review(),
        session_feedback=build_session_feedback_for_test(severity="risk"),
    )

    assert adjustment.status == "suggested"
    assert adjustment.action == "protect_rest"
    assert adjustment.suggested_session_type == "rest"


def test_build_next_session_adjustment_ignores_risky_feedback_for_easy_session():
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "run", "session_type": "endurance"},
        suggested_session=None,
        activity_review=_empty_review(),
        session_feedback=build_session_feedback_for_test(severity="risk"),
    )

    assert adjustment.status == "none"


def test_build_next_session_adjustment_rest_day_default_never_says_follow_the_session():
    """Regression #132: the no-op fallback for a rest day must not read as "follow the
    planned session" — there is no session, and pairing that text with a risk insight
    reads as an instruction to train.
    """
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "rest", "session_type": "rest", "target_duration_s": 0},
        suggested_session=None,
        activity_review=_rest_review_with_risk_insight(),
        session_feedback=None,
    )

    assert "suis la séance prévue" not in adjustment.instruction.lower()
    assert adjustment.target_session is not None


def test_build_next_session_adjustment_eases_hard_session_after_watch_feedback():
    adjustment = build_next_session_adjustment(
        planned_session={"sport": "bike", "session_type": "threshold"},
        suggested_session=None,
        activity_review=_empty_review(),
        session_feedback=build_session_feedback_for_test(severity="watch"),
    )

    assert adjustment.status == "suggested"
    assert adjustment.action == "ease"
    assert adjustment.suggested_session_type == "endurance"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_hides_adjustment_already_ignored(mock_db_fn):
    db = _mock_db_with(
        hrv={"hrv_rmssd": 25, "hrv_status": "low", "hrv_weekly_avg": 40},
        sleep={"sleep_duration_s": 6.2 * 3600, "sleep_score": 60},
        planned={"id": "s1", "sport": "run", "session_type": "intervals"},
        adjustment_decision={"decision": "ignored"},
    )
    mock_db_fn.return_value = db

    briefing = compute_briefing("u1", today=date(2026, 5, 20))

    assert briefing.suggested_session is not None
    assert briefing.next_session_adjustment.status == "none"
    assert briefing.next_session_adjustment.title == "Ajustement déjà traité"


def build_session_feedback_for_test(severity="risk"):
    return SessionFeedback(
        activity_date="2026-05-19",
        sport="run",
        planned_sport="run",
        planned_session_type="threshold",
        verdict="too_intense",
        severity=severity,
        message="Séance plus intense que prévu : évite d'empiler une autre séance dure.",
        readiness_impact=-10,
    )


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_ready_with_good_signals(mock_db_fn):
    """All signals fine -> ready status, score = baseline (no penalties applied)."""
    db = _mock_db_with(
        hrv={"hrv_rmssd": 45, "hrv_status": "balanced", "hrv_weekly_avg": 42},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily={"resting_hr": 55, "body_battery_low": 60},
        tsb=2.0,
        planned={"sport": "run", "session_type": "endurance"},
        baseline_rows=[{"resting_hr": 54}, {"resting_hr": 55}, {"resting_hr": 56}],
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.status == "ready"
    assert b.readiness_score == BASELINE_SCORE
    assert b.suggested_session is None
    assert b.planned_session is not None
    assert b.activity_review.activities_7d == 0
    assert b.coach_recommendation.action == "maintain"
    assert b.next_session_adjustment.status == "none"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_caution_with_low_hrv(mock_db_fn):
    db = _mock_db_with(
        hrv={"hrv_rmssd": 25, "hrv_status": "low", "hrv_weekly_avg": 40},
        sleep={"sleep_duration_s": 6.2 * 3600, "sleep_score": 60},
        daily=None,
        tsb=None,
        planned={"sport": "run", "session_type": "intervals"},
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))
    # Penalties: hrv_very_low(-25) + hrv_status_bad(-15) + sleep_short(-5) = -45
    # Score = 80 - 45 = 35 -> rest_advised
    assert b.status == "rest_advised"
    assert b.suggested_session is not None
    assert b.suggested_session.session_type == "rest"
    assert b.next_session_adjustment.status == "suggested"
    assert b.next_session_adjustment.suggested_session_type == "rest"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_downgrades_hard_session_when_recovery_signal_is_bad(mock_db_fn):
    db = _mock_db_with(
        hrv={"hrv_rmssd": 33, "hrv_status": "balanced", "hrv_weekly_avg": 40},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily=None,
        tsb=None,
        planned={"sport": "run", "session_type": "intervals"},
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))

    factor_names = {f.name for f in b.factors}
    assert "hrv_low" in factor_names
    assert "hard_session_guardrail" in factor_names
    assert b.status == "caution"
    assert b.suggested_session is not None
    assert b.suggested_session.session_type == "threshold"
    assert b.next_session_adjustment.status == "suggested"
    assert b.next_session_adjustment.suggested_session_type == "threshold"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_no_data_returns_ready_default(mock_db_fn):
    """Without any biometric data, default to ready (baseline score)."""
    db = _mock_db_with()
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.status == "ready"
    assert b.readiness_score == BASELINE_SCORE
    assert b.planned_session is None
    assert b.suggested_session is None
    assert b.next_session_adjustment.status == "none"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_tsb_very_negative_pushes_to_rest(mock_db_fn):
    db = _mock_db_with(
        hrv=None,
        sleep=None,
        daily=None,
        tsb=-35.0,
        planned={"sport": "bike", "session_type": "long"},
    )
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    # baseline 80 + tsb_very_negative -15 = 65 -> caution
    assert b.status == "caution"
    assert b.suggested_session is not None
    assert b.suggested_session.session_type == "endurance"
    assert b.next_session_adjustment.status == "suggested"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_activity_load_spike_affects_readiness(mock_db_fn):
    activities = [
        {"start_time": "2026-05-19T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 95},
        {
            "start_time": "2026-05-18T08:00:00Z",
            "sport": "bike",
            "duration_s": 3 * 3600,
            "tss": 130,
        },
        {"start_time": "2026-05-08T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
        {"start_time": "2026-05-01T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
        {"start_time": "2026-04-24T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
    ]
    db = _mock_db_with(
        hrv={"hrv_rmssd": 42, "hrv_status": "balanced", "hrv_weekly_avg": 42},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily={"resting_hr": 55, "body_battery_low": 60},
        tsb=2.0,
        planned={
            "sport": "run",
            "session_type": "threshold",
            "target_duration_s": 3600,
            "target_tss": 60,
            "target_elevation_gain_m": 100,
        },
        baseline_rows=[{"resting_hr": 55}],
        activities=activities,
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))

    factor_names = {f.name for f in b.factors}
    assert "activity_load_spike" in factor_names
    assert "activity_recent_long_session" in factor_names
    assert "session_feedback_too_intense" in factor_names
    assert b.readiness_score < BASELINE_SCORE
    assert b.activity_review.activities_7d == 2
    assert b.last_session_feedback is not None
    assert b.last_session_feedback.verdict == "too_intense"
    assert b.coach_recommendation.action in {"caution", "ease"}
    assert b.next_session_adjustment.status == "suggested"


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_rest_day_with_load_spike_never_says_execute_the_session(mock_db_fn):
    """Regression #132, prod repro: a rest day where activity_load_spike (near-permanent
    risk insight) is present must not tell the athlete to execute/follow "the session".
    """
    activities = [
        {"start_time": "2026-05-19T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 95},
        {
            "start_time": "2026-05-18T08:00:00Z",
            "sport": "bike",
            "duration_s": 3 * 3600,
            "tss": 130,
        },
        {"start_time": "2026-05-08T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
        {"start_time": "2026-05-01T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
        {"start_time": "2026-04-24T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 90},
    ]
    db = _mock_db_with(
        hrv={"hrv_rmssd": 42, "hrv_status": "balanced", "hrv_weekly_avg": 42},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily={"resting_hr": 55, "body_battery_low": 60},
        tsb=2.0,
        planned={"sport": "rest", "session_type": "rest", "target_duration_s": 0},
        baseline_rows=[{"resting_hr": 55}],
        activities=activities,
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))

    factor_names = {f.name for f in b.factors}
    assert "activity_load_spike" in factor_names
    assert b.is_rest_day is True
    assert b.coach_recommendation.action == "rest"
    assert "exécute la séance" not in b.coach_recommendation.instruction.lower()
    assert "suis la séance prévue" not in b.next_session_adjustment.instruction.lower()


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_skips_stale_session_feedback(mock_db_fn):
    """A latest activity older than the recency window must not drive post-session feedback.

    Regression: a bike done on a planned rest day kept resurfacing 'trained on rest day' in
    later briefings because the latest *synced* activity can be several days old (sync lag).
    """
    activities = [
        # 3 days before the briefing date -> outside the 2-day window
        {"start_time": "2026-05-17T08:00:00Z", "sport": "bike", "duration_s": 3600, "tss": 60},
    ]
    db = _mock_db_with(
        hrv={"hrv_rmssd": 42, "hrv_status": "balanced", "hrv_weekly_avg": 42},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily={"resting_hr": 55, "body_battery_low": 60},
        tsb=2.0,
        planned={"sport": "rest", "session_type": "rest"},
        baseline_rows=[{"resting_hr": 55}],
        activities=activities,
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))

    assert b.last_session_feedback is None
    assert not any(f.name.startswith("session_feedback_") for f in b.factors)


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_keeps_recent_session_feedback(mock_db_fn):
    """A latest activity within the 2-day window still produces post-session feedback."""
    activities = [
        # exactly 2 days before the briefing date -> inside the window
        {"start_time": "2026-05-18T08:00:00Z", "sport": "bike", "duration_s": 3600, "tss": 60},
    ]
    db = _mock_db_with(
        hrv={"hrv_rmssd": 42, "hrv_status": "balanced", "hrv_weekly_avg": 42},
        sleep={"sleep_duration_s": 7.5 * 3600, "sleep_score": 75},
        daily={"resting_hr": 55, "body_battery_low": 60},
        tsb=2.0,
        planned={"sport": "run", "session_type": "endurance", "target_duration_s": 3600},
        baseline_rows=[{"resting_hr": 55}],
        activities=activities,
    )
    mock_db_fn.return_value = db

    b = compute_briefing("u1", today=date(2026, 5, 20))

    assert b.last_session_feedback is not None
    assert b.last_session_feedback.verdict == "sport_mismatch"
    # Regression #127 (briefing part): a sport swap is an observance signal, not a
    # fatigue one — it must not be folded into readiness_score.
    assert b.readiness_score == BASELINE_SCORE
    assert not any(f.name.startswith("session_feedback_") for f in b.factors)


def test_dailybriefing_to_dict_serializes_factors_and_suggestion():
    b = DailyBriefing(
        date="2026-05-20",
        readiness_score=55,
        status="caution",
        explanation_md="x",
        factors=[ReadinessFactor("hrv_low", -10, "ok")],
        planned_session={"sport": "run"},
        suggested_session=SuggestedSession(sport="run", session_type="endurance", note="ok"),
        activity_review=_empty_review(),
        last_session_feedback=None,
        coach_recommendation=CoachRecommendation(
            action="ease",
            title="Séance allégée",
            rationale="ok",
            instruction="Z2 facile.",
        ),
        next_session_adjustment=_no_next_adjustment(),
    )
    d = b.to_dict()
    assert d["readiness_score"] == 55
    assert d["status"] == "caution"
    assert d["factors"][0]["name"] == "hrv_low"
    assert d["suggested_session"]["session_type"] == "endurance"
    assert d["activity_review"]["lookback_days"] == 90
    assert d["last_session_feedback"] is None
    assert d["coach_recommendation"]["action"] == "ease"
    assert d["next_session_adjustment"]["action"] == "maintain"
    assert d["is_rest_day"] is False


def test_dailybriefing_to_dict_exposes_is_rest_day():
    b = DailyBriefing(
        date="2026-05-20",
        readiness_score=80,
        status="ready",
        explanation_md="x",
        factors=[],
        planned_session={"sport": "rest", "session_type": "rest"},
        suggested_session=None,
        activity_review=_empty_review(),
        last_session_feedback=None,
        coach_recommendation=CoachRecommendation(
            action="rest",
            title="Repos",
            rationale="ok",
            instruction="Récupère.",
        ),
        next_session_adjustment=_no_next_adjustment(),
        is_rest_day=True,
    )
    assert b.to_dict()["is_rest_day"] is True


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_get_cached_daily_briefing_returns_payload_for_current_logic_version(mock_db_fn):
    payload = {"date": "2026-05-20", "readiness_score": 80}
    db = MagicMock()
    query = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    query.maybe_single.return_value.execute.return_value.data = {
        "logic_version": BRIEFING_CACHE_VERSION,
        "payload": payload,
    }
    mock_db_fn.return_value = db

    assert get_cached_daily_briefing("u1", today=date(2026, 5, 20)) == payload


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_get_cached_daily_briefing_ignores_stale_logic_version(mock_db_fn):
    db = MagicMock()
    query = db.table.return_value.select.return_value.eq.return_value.eq.return_value
    query.maybe_single.return_value.execute.return_value.data = {
        "logic_version": "old",
        "payload": {"date": "2026-05-20", "readiness_score": 80},
    }
    mock_db_fn.return_value = db

    assert get_cached_daily_briefing("u1", today=date(2026, 5, 20)) is None


def _recovery_row(**overrides):
    base = {
        "baseline": None,
        "recent": None,
        "trend": "no_data",
        "confidence": "no_data",
        "freshness": "no_data",
        "days_covered": 0,
        "last_date": None,
    }
    row = {k: dict(base) for k in ("hrv", "resting_hr", "sleep", "stress", "body_battery", "steps")}
    row.update(overrides)
    return row


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_resting_hr_from_recovery_baseline(mock_db_fn):
    # resting_hr baseline 48, today 56 (> baseline*1.10) -> resting_hr_high penalty.
    rb = _recovery_row(
        resting_hr={
            "baseline": 48.0,
            "recent": 56.0,
            "trend": "declining",
            "confidence": "high",
            "freshness": "fresh",
            "days_covered": 28,
            "last_date": "2026-05-19",
        }
    )
    db = _mock_db_with(daily={"resting_hr": 56, "body_battery_low": 60}, recovery_baselines=rb)
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.readiness_score < BASELINE_SCORE


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_falls_back_without_recovery_row(mock_db_fn):
    db = _mock_db_with(recovery_baselines=None)
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert isinstance(b.readiness_score, int)
    assert 0 <= b.readiness_score <= 100


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_stress_high_against_baseline(mock_db_fn):
    rb = _recovery_row(
        stress={
            "baseline": 30.0,
            "recent": 55.0,
            "trend": "declining",
            "confidence": "high",
            "freshness": "fresh",
            "days_covered": 28,
            "last_date": "2026-05-19",
        }
    )
    db = _mock_db_with(
        daily={"resting_hr": 50, "stress_avg": 55, "body_battery_low": 60},
        recovery_baselines=rb,
    )
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.readiness_score < BASELINE_SCORE


def test_score_steps_no_daily_returns_empty():
    assert _score_steps(None, 8000.0) == []


def test_score_steps_no_baseline_returns_empty():
    assert _score_steps({"steps": 15000}, None) == []
    assert _score_steps({"steps": 15000}, 0.0) == []


def test_score_steps_missing_value_returns_empty():
    assert _score_steps({}, 8000.0) == []


def test_score_steps_below_threshold_returns_empty():
    # 8000 * 1.5 = 12000 ; 11000 <= 12000 -> pas de facteur
    assert _score_steps({"steps": 11000}, 8000.0) == []


def test_score_steps_above_threshold_returns_penalty():
    factors = _score_steps({"steps": 13000}, 8000.0)
    assert len(factors) == 1
    assert factors[0].name == "steps_high"
    assert factors[0].impact == -5


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_steps_high_against_baseline(mock_db_fn):
    rb = _recovery_row(
        steps={
            "baseline": 8000.0,
            "recent": 13000.0,
            "trend": "declining",
            "confidence": "high",
            "freshness": "fresh",
            "days_covered": 28,
            "last_date": "2026-05-19",
        }
    )
    db = _mock_db_with(
        daily={"resting_hr": 50, "stress_avg": 30, "body_battery_low": 60, "steps": 13000},
        recovery_baselines=rb,
    )
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.readiness_score == BASELINE_SCORE - 5
    assert any(f.name == "steps_high" for f in b.factors)


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_sleep_below_personal_baseline(mock_db_fn):
    rb = _recovery_row(
        sleep={
            "baseline": 80.0,
            "recent": 60.0,
            "trend": "declining",
            "confidence": "high",
            "freshness": "fresh",
            "days_covered": 28,
            "last_date": "2026-05-19",
            "duration_baseline_s": 28800,
            "score_baseline": 85,
        }
    )
    db = _mock_db_with(
        sleep={"sleep_duration_s": 5 * 3600, "sleep_score": 70},
        daily={"resting_hr": 50, "body_battery_low": 60},
        recovery_baselines=rb,
    )
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.readiness_score < BASELINE_SCORE


@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_briefing_body_battery_below_personal_baseline(mock_db_fn):
    rb = _recovery_row(
        body_battery={
            "baseline": 90.0,
            "recent": 60.0,
            "trend": "declining",
            "confidence": "high",
            "freshness": "fresh",
            "days_covered": 28,
            "last_date": "2026-05-19",
        }
    )
    db = _mock_db_with(
        daily={"resting_hr": 50, "body_battery_low": 60, "body_battery_high": 60},
        recovery_baselines=rb,
    )
    mock_db_fn.return_value = db
    b = compute_briefing("u1", today=date(2026, 5, 20))
    assert b.readiness_score < BASELINE_SCORE


@patch("garmin_sync.coach.briefing.compute_briefing")
@patch("garmin_sync.coach.briefing.get_admin_client")
def test_compute_and_cache_daily_briefing_upserts_payload(mock_db_fn, mock_compute):
    briefing = DailyBriefing(
        date="2026-05-20",
        readiness_score=80,
        status="ready",
        explanation_md="Bonne disponibilité.",
        factors=[],
        planned_session=None,
        suggested_session=None,
        activity_review=_empty_review(),
        last_session_feedback=None,
        coach_recommendation=CoachRecommendation(
            action="maintain",
            title="Séance maintenue",
            rationale="ok",
            instruction="Reste facile.",
        ),
        next_session_adjustment=_no_next_adjustment(),
    )
    db = MagicMock()
    mock_db_fn.return_value = db
    mock_compute.return_value = briefing

    payload = compute_and_cache_daily_briefing("u1", today=date(2026, 5, 20))

    assert payload["readiness_score"] == 80
    db.table.return_value.upsert.assert_called_once()
    upsert_payload = db.table.return_value.upsert.call_args.args[0]
    assert upsert_payload["user_id"] == "u1"
    assert upsert_payload["briefing_date"] == "2026-05-20"
    assert upsert_payload["logic_version"] == BRIEFING_CACHE_VERSION
    assert db.table.return_value.upsert.call_args.kwargs["on_conflict"] == "user_id,briefing_date"
