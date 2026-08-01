from garmin_sync.coach.session_feedback import build_session_feedback


def _activity(**overrides):
    row = {
        "start_time": "2026-05-20T08:00:00Z",
        "sport": "run",
        "duration_s": 3600,
        "tss": 60,
        "elevation_gain_m": 100,
    }
    row.update(overrides)
    return row


def _planned(**overrides):
    row = {
        "date": "2026-05-20",
        "sport": "run",
        "session_type": "endurance",
        "target_duration_s": 3600,
        "target_tss": 60,
        "target_elevation_gain_m": 100,
    }
    row.update(overrides)
    return row


def test_session_feedback_well_executed():
    feedback = build_session_feedback(activity=_activity(), planned_session=_planned())

    assert feedback is not None
    assert feedback.verdict == "well_executed"
    assert feedback.severity == "positive"
    assert feedback.readiness_impact > 0


def test_session_feedback_too_intense_penalizes_readiness():
    feedback = build_session_feedback(
        activity=_activity(tss=95),
        planned_session=_planned(target_tss=60),
    )

    assert feedback is not None
    assert feedback.verdict == "too_intense"
    assert feedback.severity == "risk"
    assert feedback.readiness_impact == -10


def test_session_feedback_too_long():
    feedback = build_session_feedback(
        activity=_activity(duration_s=5400, tss=65),
        planned_session=_planned(target_duration_s=3600, target_tss=60),
    )

    assert feedback is not None
    assert feedback.verdict == "too_long"
    assert feedback.readiness_impact == -5


def test_session_feedback_too_short_without_compensation():
    feedback = build_session_feedback(
        activity=_activity(duration_s=1800, tss=35),
        planned_session=_planned(target_duration_s=3600, target_tss=60),
    )

    assert feedback is not None
    assert feedback.verdict == "too_short"
    assert feedback.severity == "watch"


def test_session_feedback_more_elevation():
    feedback = build_session_feedback(
        activity=_activity(elevation_gain_m=250, tss=60),
        planned_session=_planned(target_elevation_gain_m=100),
    )

    assert feedback is not None
    assert feedback.verdict == "more_elevation"
    assert feedback.readiness_impact == -5


def test_session_feedback_trained_on_rest_day():
    feedback = build_session_feedback(
        activity=_activity(sport="bike"),
        planned_session=_planned(sport="rest", session_type="rest", target_duration_s=0),
    )

    assert feedback is not None
    assert feedback.verdict == "trained_on_rest_day"
    assert "repos" in feedback.message.lower()


def test_session_feedback_sport_mismatch_does_not_penalize_readiness():
    """Regression #127 (briefing part): swapping the day's sport is a planning divergence,
    not a fatigue signal. It must not move readiness_score, only stay visible as
    observance info (verdict/message) with a neutral readiness_impact.
    """
    feedback = build_session_feedback(
        activity=_activity(sport="swim"),
        planned_session=_planned(sport="bike", session_type="endurance"),
    )

    assert feedback is not None
    assert feedback.verdict == "sport_mismatch"
    assert feedback.severity == "watch"
    assert feedback.readiness_impact == 0


def test_session_feedback_unplanned_activity():
    feedback = build_session_feedback(activity=_activity(), planned_session=None)

    assert feedback is not None
    assert feedback.verdict == "unplanned"
    assert feedback.planned_sport is None


def test_session_feedback_ignores_invalid_activity_dates():
    assert (
        build_session_feedback(activity=_activity(start_time="not-a-date"), planned_session=None)
        is None
    )
    assert build_session_feedback(activity=_activity(start_time=None), planned_session=None) is None


def test_session_feedback_sport_equivalence_accepts_garmin_names():
    feedback = build_session_feedback(
        activity=_activity(sport="trail_running"),
        planned_session=_planned(sport="run"),
    )

    assert feedback is not None
    assert feedback.verdict == "well_executed"


def test_session_feedback_serializes_payload():
    feedback = build_session_feedback(activity=_activity(), planned_session=_planned())

    assert feedback is not None
    payload = feedback.to_dict()
    assert payload["activity_date"] == "2026-05-20"
    assert payload["verdict"] == "well_executed"
