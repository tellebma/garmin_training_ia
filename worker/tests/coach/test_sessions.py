from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.activity_review import ActivityInsight, ActivityReview
from garmin_sync.coach.openai_client import LlmUsage, OpenAIError, WorkoutResult
from garmin_sync.coach.sessions import (
    SessionNotFound,
    _inject_effective_strengths,
    ensure_sessions,
    regenerate_session,
)


def _mock_workout():
    return {
        "warmup": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "main": [{"duration_s": 1800, "target": {"label": "Z2", "rpe": 4}, "notes": None}],
        "cooldown": {"duration_s": 600, "target": {"label": "Z1", "rpe": 2}, "notes": None},
        "summary_md": "ok",
        "technical_focus": None,
    }


def _workout_result(workout_dict=None):
    return WorkoutResult(
        workout=MagicMock(model_dump=lambda: workout_dict or _mock_workout()),
        usage=LlmUsage(model="gpt-4o-mini", prompt_tokens=100, completion_tokens=50),
    )


def _planned_select_chain(db):
    """Return the chain object that .data is set on for the pending planned_sessions query."""
    return db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.lte.return_value.execute.return_value  # noqa: E501


def _profile_chain(db):
    return db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501


def _race_chain(db):
    return db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_skips_already_generated(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = []
    result = ensure_sessions(user_id="u1", days=7)
    assert result == {
        "generated_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "deferred_count": 0,
    }
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_generates_for_each_pending(
    mock_db,
    mock_gen,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "endurance",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        },
        {
            "id": "s2",
            "sport": "bike",
            "session_type": "long",
            "target_duration_s": 7200,
            "target_tss": 120,
            "phase": "base",
            "date": "2026-05-22",
        },
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = {
        "discipline": "triathlon",
        "total_elevation_gain_m": 350,
        "race_date": "2026-08-15",
    }

    mock_gen.return_value = _workout_result()

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 2
    assert mock_gen.call_count == 2
    assert mock_record.call_count == 2


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_records_usage_on_total_failure(
    mock_db,
    mock_gen,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    """3 tentatives brûlées = 3 requêtes facturées : le coût doit être enregistré
    en status 'failed'. Sans ça il disparaît du finops (écart 622 req / 11 lignes)."""
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "endurance",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        }
    ]
    _profile_chain(db).data = {"fc_max_bpm": 195, "sports_strengths": {"run": 3}}
    _race_chain(db).data = {
        "discipline": "triathlon",
        "total_elevation_gain_m": 350,
        "race_date": "2026-08-15",
    }

    err = OpenAIError("OpenAI returned unrealistic workout: warmup too long")
    err.usage = LlmUsage(model="gpt-4o-mini", prompt_tokens=900, completion_tokens=300)
    err.attempts = 3
    mock_gen.side_effect = err

    result = ensure_sessions(user_id="u1", days=7)

    assert result["failed_count"] == 1
    assert result["generated_count"] == 0
    mock_record.assert_called_once_with(
        user_id="u1",
        feature="session_workout",
        model="gpt-4o-mini",
        prompt_tokens=900,
        completion_tokens=300,
        attempts=3,
        status="failed",
        session_id="s1",
    )


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_skips_rest_days(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "rest-1",
            "sport": "rest",
            "session_type": "rest",
            "target_duration_s": 0,
            "target_tss": 0,
            "phase": "base",
            "date": "2026-05-21",
        }
    ]

    result = ensure_sessions(user_id="u1", days=7)

    assert result == {
        "generated_count": 0,
        "failed_count": 0,
        "skipped_count": 1,
        "deferred_count": 0,
    }
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_continues_on_error(
    mock_db,
    mock_gen,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "endurance",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        },
        {
            "id": "s2",
            "sport": "bike",
            "session_type": "long",
            "target_duration_s": 7200,
            "target_tss": 120,
            "phase": "base",
            "date": "2026-05-22",
        },
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = None  # no active race

    from garmin_sync.coach.openai_client import OpenAIError

    mock_gen.side_effect = [OpenAIError("boom"), _workout_result()]

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 1
    assert result["failed_count"] == 1
    mock_record.assert_called_once()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.capture")
@patch("garmin_sync.coach.sessions._load_activity_review")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_reports_failure_to_sentry(
    mock_db,
    mock_gen,
    mock_review,
    mock_capture,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "endurance",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        },
    ]
    _profile_chain(db).data = {"sports_strengths": {"swim": 2, "bike": 4, "run": 3}}
    _race_chain(db).data = None
    mock_review.return_value = ActivityReview(
        lookback_days=90,
        activities_7d=0,
        activities_28d=0,
        tss_7d=0,
        avg_weekly_tss_prev_21d=0,
        elevation_gain_7d=0,
        avg_weekly_elevation_prev_21d=0,
        sport_counts_28d={},
        days_since_last_activity=None,
        insights=[],
    )

    from garmin_sync.coach.openai_client import OpenAIError

    mock_gen.side_effect = OpenAIError("unrealistic workout: warmup exceeds cap")

    ensure_sessions(user_id="u1", days=7)

    mock_capture.assert_called_once()
    assert mock_capture.call_args.kwargs["where"] == "ensure_sessions"
    assert mock_capture.call_args.kwargs["session_id"] == "s1"


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions._load_activity_review")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_passes_activity_review_to_generation(
    mock_db,
    mock_gen,
    mock_review,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "intervals",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        }
    ]
    _profile_chain(db).data = {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = {
        "discipline": "triathlon",
        "total_elevation_gain_m": 350,
        "race_date": "2026-08-15",
    }
    mock_review.return_value = ActivityReview(
        lookback_days=90,
        activities_7d=2,
        activities_28d=6,
        tss_7d=220,
        avg_weekly_tss_prev_21d=120,
        elevation_gain_7d=800,
        avg_weekly_elevation_prev_21d=300,
        sport_counts_28d={"run": 4, "bike": 2},
        days_since_last_activity=1,
        insights=[
            ActivityInsight(
                "load_spike",
                "risk",
                "Charge récente nettement au-dessus de la tendance.",
                -10,
            )
        ],
    )
    mock_gen.return_value = _workout_result()

    result = ensure_sessions(user_id="u1", days=7)

    assert result["generated_count"] == 1
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["race_context"]["activity_review"]["activities_7d"] == 2
    assert "coach_context" in call_kwargs["session"]
    assert "Charge récente" in call_kwargs["session"]["coach_context"]
    assert "Ajustement coach proposé" in call_kwargs["session"]["coach_context"]
    assert "baisse l'intensité" in call_kwargs["session"]["coach_context"]
    mock_record.assert_called_once()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_updates_existing(
    mock_db,
    mock_gen,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    # session lookup
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = {
        "id": "s1",
        "user_id": "u1",
        "sport": "run",
        "session_type": "intervals",
        "target_duration_s": 3600,
        "target_tss": 80,
        "phase": "peak",
        "date": "2026-05-25",
    }
    _profile_chain(db).data = {
        "ftp_watts": 240,
        "vma_kmh": 17.0,
        "fc_max_bpm": 195,
        "sports_strengths": {"swim": 2, "bike": 4, "run": 3},
    }
    _race_chain(db).data = None
    mock_gen.return_value = _workout_result()

    result = regenerate_session(user_id="u1", session_id="s1")
    assert result["status"] == "ok"
    mock_gen.assert_called_once()
    mock_record.assert_called_once_with(
        user_id="u1",
        feature="session_workout",
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        attempts=1,
        status="ok",
        session_id="s1",
    )


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_skips_rest_day(mock_db, mock_gen):
    db = MagicMock()
    mock_db.return_value = db
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = {
        "id": "rest-1",
        "user_id": "u1",
        "sport": "rest",
        "session_type": "rest",
        "target_duration_s": 0,
        "target_tss": 0,
        "phase": "base",
        "date": "2026-05-25",
    }

    result = regenerate_session(user_id="u1", session_id="rest-1")

    assert result == {"status": "ok", "workout": None, "skipped": True}
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_not_found_for_user(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = None
    with pytest.raises(SessionNotFound):
        regenerate_session(user_id="u1", session_id="other-id")


def test_inject_effective_strengths_overwrites_declared_with_effective() -> None:
    # run déclaré 4 mais ~0 activité sur 90j -> descendu à 3.
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value  # noqa: E501
    chain.data = []  # pas d'activité
    athlete = {"sports_strengths": {"swim": 2, "bike": 4, "run": 4}, "ftp_watts": 240}
    out = _inject_effective_strengths(db, "u1", athlete, today=date(2026, 6, 28))
    # sans activité -> safe noop : effectif == déclaré (borné), donc inchangé ici
    assert out["sports_strengths"] == {"swim": 2, "bike": 4, "run": 4}


@patch("garmin_sync.coach.sessions.load_effective_strengths")
def test_inject_effective_strengths_uses_reconciled_levels(mock_load) -> None:
    mock_load.return_value = {"swim": 2, "bike": 5, "run": 3}
    db = MagicMock()
    athlete = {"sports_strengths": {"swim": 2, "bike": 4, "run": 3}, "ftp_watts": 240}
    out = _inject_effective_strengths(db, "u1", athlete)
    assert out["sports_strengths"] == {"swim": 2, "bike": 5, "run": 3}
    # le reste du profil est préservé
    assert out["ftp_watts"] == 240


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=False)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_skips_generation_when_kill_switch_off(
    mock_db,
    mock_gen,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [
        {
            "id": "s1",
            "sport": "run",
            "session_type": "endurance",
            "target_duration_s": 3000,
            "target_tss": 50,
            "phase": "base",
            "date": "2026-05-21",
        },
    ]

    result = ensure_sessions(user_id="u1", days=7)

    mock_gen.assert_not_called()
    assert result["generated_count"] == 0
    assert result["skipped_count"] == 1
    assert result["llm_generation_disabled"] is True


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=False)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_returns_disabled_status_when_kill_switch_off(
    mock_db,
    mock_gen,
    _mock_flag,  # noqa: PT019
):
    db = MagicMock()
    mock_db.return_value = db
    session_lookup = db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    session_lookup.data = {
        "id": "s1",
        "user_id": "u1",
        "sport": "run",
        "session_type": "intervals",
        "target_duration_s": 3600,
        "target_tss": 80,
        "phase": "peak",
        "date": "2026-05-25",
    }

    result = regenerate_session(user_id="u1", session_id="s1")

    assert result == {"status": "generation_disabled"}
    mock_gen.assert_not_called()


def _pending_session(session_id: str = "s1", **overrides) -> dict:
    base = {
        "id": session_id,
        "sport": "run",
        "session_type": "endurance",
        "target_duration_s": 3000,
        "target_tss": 50,
        "phase": "base",
        "date": "2026-07-03",
        "workout_generation_failed_at": None,
    }
    return {**base, **overrides}


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_defers_recently_failed(mock_db, mock_gen):
    from datetime import UTC, datetime, timedelta

    db = MagicMock()
    mock_db.return_value = db
    recent_fail = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _planned_select_chain(db).data = [
        _pending_session("s1", workout_generation_failed_at=recent_fail)
    ]

    result = ensure_sessions(user_id="u1", days=7)

    assert result["deferred_count"] == 1
    assert result["generated_count"] == 0
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_retries_after_backoff_expiry(
    mock_db,
    mock_gen,
    mock_record,
    _mock_flag,  # noqa: PT019
):
    from datetime import UTC, datetime, timedelta

    db = MagicMock()
    mock_db.return_value = db
    old_fail = (datetime.now(UTC) - timedelta(hours=7)).isoformat()
    _planned_select_chain(db).data = [_pending_session("s1", workout_generation_failed_at=old_fail)]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.return_value = _workout_result()

    result = ensure_sessions(user_id="u1", days=7)

    assert result["generated_count"] == 1
    assert result["deferred_count"] == 0


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_backoff_tolerates_naive_timestamp(mock_db, mock_gen):
    """Un timestamp sans offset (naïf) ne doit pas crasher ensure_sessions :
    il est interprété comme UTC et le backoff s'applique."""
    from datetime import UTC, datetime, timedelta

    db = MagicMock()
    mock_db.return_value = db
    naive_recent = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    _planned_select_chain(db).data = [
        _pending_session("s1", workout_generation_failed_at=naive_recent)
    ]

    result = ensure_sessions(user_id="u1", days=7)

    assert result["deferred_count"] == 1
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_generation_failure_marks_backoff(mock_db, mock_gen, _mock_flag):  # noqa: PT019
    from garmin_sync.coach.openai_client import OpenAIError

    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [_pending_session("s1")]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.side_effect = OpenAIError("boom")

    result = ensure_sessions(user_id="u1", days=7)

    assert result["failed_count"] == 1
    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    assert any(isinstance(p.get("workout_generation_failed_at"), str) for p in update_payloads)


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_backoff_marking_failure_does_not_abort_loop(mock_db, mock_gen, _mock_flag):  # noqa: PT019
    """Si l'update du marqueur d'échec lève, ensure_sessions contient l'erreur."""
    from garmin_sync.coach.openai_client import OpenAIError

    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [_pending_session("s1")]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.side_effect = OpenAIError("boom")
    db.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception(
        "db down"
    )

    result = ensure_sessions(user_id="u1", days=7)

    assert result["failed_count"] == 1


@patch("garmin_sync.coach.sessions.is_flag_active", return_value=True)
@patch("garmin_sync.coach.sessions.record_llm_usage")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_generation_success_resets_backoff(mock_db, mock_gen, mock_record, _mock_flag):  # noqa: PT019
    db = MagicMock()
    mock_db.return_value = db
    _planned_select_chain(db).data = [_pending_session("s1")]
    _profile_chain(db).data = {"sports_strengths": {"swim": 3, "bike": 3, "run": 3}}
    _race_chain(db).data = None
    mock_gen.return_value = _workout_result()

    ensure_sessions(user_id="u1", days=7)

    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    success = next(p for p in update_payloads if "workout" in p)
    assert success["workout_generation_failed_at"] is None
