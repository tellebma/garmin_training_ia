from unittest.mock import MagicMock, patch

import pytest

from garmin_sync.coach.rate_limit import (
    ENSURE_SESSIONS,
    REGENERATE_SESSION,
    RateLimit,
    RateLimited,
    check_or_raise,
)


@patch("garmin_sync.coach.rate_limit.get_admin_client")
def test_check_or_raise_passes_when_allowed(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    db.rpc.return_value.execute.return_value.data = True

    check_or_raise(user_id="u1", limit=ENSURE_SESSIONS)
    db.rpc.assert_called_once_with(
        "check_and_log_coach_rate_limit",
        {
            "p_user_id": "u1",
            "p_action": "ensure_sessions",
            "p_max_count": 60,
            "p_window_seconds": 3600,
        },
    )


@patch("garmin_sync.coach.rate_limit.get_admin_client")
def test_check_or_raise_raises_when_denied(mock_db):
    db = MagicMock()
    mock_db.return_value = db
    db.rpc.return_value.execute.return_value.data = False

    with pytest.raises(RateLimited):
        check_or_raise(user_id="u1", limit=REGENERATE_SESSION)


def test_rate_limit_definitions_have_sane_bounds():
    assert ENSURE_SESSIONS.max_count >= 1
    assert ENSURE_SESSIONS.window_seconds >= 60
    assert REGENERATE_SESSION.max_count >= 1
    assert REGENERATE_SESSION.window_seconds >= 60
    # Regen should be stricter than ensure (cost-bearing user action).
    assert REGENERATE_SESSION.max_count < ENSURE_SESSIONS.max_count


def test_custom_rate_limit_struct_is_immutable():
    from dataclasses import FrozenInstanceError

    custom = RateLimit(action="x", max_count=1, window_seconds=60)
    with pytest.raises(FrozenInstanceError):
        custom.max_count = 999  # type: ignore[misc]
