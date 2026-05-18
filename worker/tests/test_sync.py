"""Tests for per-user sync orchestration with mocked Garmin + Supabase."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_sync.sync import sync_user_for_date_range


@pytest.fixture
def fake_garmin_client() -> MagicMock:
    client = MagicMock()
    client.get_activities_by_date.return_value = [
        {
            "activityId": 1,
            "startTimeGMT": "2026-05-15 07:00:00",
            "activityType": {"typeKey": "running"},
            "duration": 1800.0,
            "distance": 5000.0,
        }
    ]
    client.get_stats.return_value = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": 52,
        "totalSteps": 8000,
    }
    client.get_sleep_data.return_value = {
        "dailySleepDTO": {"calendarDate": "2026-05-15", "sleepTimeSeconds": 28800},
    }
    client.get_hrv_data.return_value = {"calendarDate": "2026-05-15", "lastNightAvg": 50.0}
    client.get_body_composition.return_value = [{"calendarDate": "2026-05-15", "weight": 70000}]
    return client


@pytest.fixture
def fake_admin_client() -> MagicMock:
    return MagicMock()


def test_sync_user_inserts_each_table(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    # 5 tables touched
    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert tables_touched >= {"activities", "daily_metrics", "sleep", "hrv", "body_composition"}


def test_sync_user_continues_when_one_endpoint_fails(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    # hrv endpoint blows up
    fake_garmin_client.get_hrv_data.side_effect = RuntimeError("garmin 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        # Should not raise — partial sync is acceptable
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "activities" in tables_touched
    assert "hrv" not in tables_touched


def test_sync_user_aborts_on_rate_limit(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A 429 is a global stop signal: do NOT continue the 90-day loop matraquant
    Garmin. The exception must bubble up so the caller can mark last_sync_status.
    """
    fake_garmin_client.get_stats.side_effect = GarminConnectTooManyRequestsError("429")

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectTooManyRequestsError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 1),
            end=date(2026, 5, 15),  # 15 days — if loop continued we'd see many calls
        )

    # Only the first day's daily call should have been attempted (then abort).
    assert fake_garmin_client.get_stats.call_count == 1
    # Subsequent endpoints in the same day must NOT have been called.
    assert fake_garmin_client.get_sleep_data.call_count == 0
    assert fake_garmin_client.get_hrv_data.call_count == 0
    assert fake_garmin_client.get_body_composition.call_count == 0


def test_sync_user_aborts_on_auth_failure(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A 401 means the token is dead. Continuing would just bombard Garmin with
    bad-token requests for every day in the range.
    """
    fake_garmin_client.get_stats.side_effect = GarminConnectAuthenticationError("401")

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectAuthenticationError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 1),
            end=date(2026, 5, 15),
        )

    assert fake_garmin_client.get_stats.call_count == 1
