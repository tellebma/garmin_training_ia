from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.activity_review import ActivityInsight, ActivityReview
from garmin_sync.coach.sessions import (
    SessionNotFound,
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
    assert result == {"generated_count": 0, "failed_count": 0, "skipped_count": 0}
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_generates_for_each_pending(mock_db, mock_gen):
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

    workout_obj = MagicMock(model_dump=lambda: _mock_workout())
    mock_gen.return_value = workout_obj

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 2
    assert mock_gen.call_count == 2


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

    assert result == {"generated_count": 0, "failed_count": 0, "skipped_count": 1}
    mock_gen.assert_not_called()


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_continues_on_error(mock_db, mock_gen):
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

    workout_obj = MagicMock(model_dump=lambda: _mock_workout())
    mock_gen.side_effect = [OpenAIError("boom"), workout_obj]

    result = ensure_sessions(user_id="u1", days=7)
    assert result["generated_count"] == 1
    assert result["failed_count"] == 1


@patch("garmin_sync.coach.sessions._load_activity_review")
@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_ensure_sessions_passes_activity_review_to_generation(mock_db, mock_gen, mock_review):
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
    mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())

    result = ensure_sessions(user_id="u1", days=7)

    assert result["generated_count"] == 1
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["race_context"]["activity_review"]["activities_7d"] == 2
    assert "coach_context" in call_kwargs["session"]
    assert "Charge récente" in call_kwargs["session"]["coach_context"]


@patch("garmin_sync.coach.sessions.generate_workout_for_session")
@patch("garmin_sync.coach.sessions.get_admin_client")
def test_regenerate_session_updates_existing(mock_db, mock_gen):
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
    mock_gen.return_value = MagicMock(model_dump=lambda: _mock_workout())

    result = regenerate_session(user_id="u1", session_id="s1")
    assert result["status"] == "ok"
    mock_gen.assert_called_once()


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
