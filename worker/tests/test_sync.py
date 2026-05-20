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


def test_sync_aborts_when_activities_endpoint_rate_limits(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """If get_activities_by_date itself returns 429, the entire sync aborts —
    we do not proceed to the per-day loop.

    Covers sync.py lines 61-65 (the abort branch of the activities try/except)."""
    fake_garmin_client.get_activities_by_date.side_effect = GarminConnectTooManyRequestsError(
        "429"
    )

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectTooManyRequestsError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 1),
            end=date(2026, 5, 15),
        )

    # No per-day endpoints should have been called after the abort
    assert fake_garmin_client.get_stats.call_count == 0
    assert fake_garmin_client.get_sleep_data.call_count == 0


def test_sync_continues_when_daily_endpoint_fails_transiently(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A transient (non-429/non-401) error in daily must be swallowed; the
    rest of the day's endpoints must still run.

    Covers sync.py lines 87-88."""
    fake_garmin_client.get_stats.side_effect = RuntimeError("garmin 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    # daily failed but sleep/hrv/body still ran
    assert "daily_metrics" not in tables_touched
    assert "sleep" in tables_touched


def test_sync_continues_when_sleep_endpoint_fails_transiently(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """Covers sync.py lines 98-101 — sleep exception fallback."""
    fake_garmin_client.get_sleep_data.side_effect = RuntimeError("garmin 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "sleep" not in tables_touched
    assert "hrv" in tables_touched


def test_sync_aborts_when_sleep_endpoint_returns_auth_error(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A 401 returned by sleep must bubble up just like one returned by daily —
    the credential is dead, continuing would just bombard Garmin.

    Covers sync.py line 98-99 (the _AbortSyncErrors branch of _safe_upsert_sleep)."""
    fake_garmin_client.get_sleep_data.side_effect = GarminConnectAuthenticationError("401")

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectAuthenticationError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 16),
        )

    # Sleep called on day 1 — and crashed — must NOT have been called on day 2
    assert fake_garmin_client.get_sleep_data.call_count == 1


def test_sync_aborts_when_hrv_endpoint_returns_rate_limit(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """Covers sync.py line 111-112 (the _AbortSyncErrors branch of _safe_upsert_hrv)."""
    fake_garmin_client.get_hrv_data.side_effect = GarminConnectTooManyRequestsError("429")

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectTooManyRequestsError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 16),
        )

    assert fake_garmin_client.get_hrv_data.call_count == 1


def test_sync_aborts_when_body_endpoint_returns_auth_error(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """Covers sync.py line 125-126 (the _AbortSyncErrors branch of _safe_upsert_body)."""
    fake_garmin_client.get_body_composition.side_effect = GarminConnectAuthenticationError("401")

    with (
        patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client),
        pytest.raises(GarminConnectAuthenticationError),
    ):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 16),
        )

    assert fake_garmin_client.get_body_composition.call_count == 1


def test_sync_continues_when_body_endpoint_fails_transiently(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A non-fatal body error must be swallowed; the per-day loop continues
    to the next day.

    Covers sync.py lines 127-128."""
    fake_garmin_client.get_body_composition.side_effect = RuntimeError("garmin 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 16),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "body_composition" not in tables_touched
    # Daily/sleep/hrv ran on both days
    assert "daily_metrics" in tables_touched


def test_sync_skips_daily_when_calendar_date_missing(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """If get_stats returns a payload without calendarDate, daily upsert must
    be skipped (the row would be invalid)."""
    fake_garmin_client.get_stats.return_value = {"foo": "bar"}  # no calendarDate

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "daily_metrics" not in tables_touched


def test_sync_skips_body_when_calendar_date_missing(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    fake_garmin_client.get_body_composition.return_value = [{"weight": 70000}]  # no calendarDate

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "body_composition" not in tables_touched


def test_sync_skips_activities_upsert_when_empty(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """If Garmin returns no activities, we should not call upsert on the
    activities table at all."""
    fake_garmin_client.get_activities_by_date.return_value = []

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "activities" not in tables_touched


def test_sync_continues_when_activities_endpoint_fails_transiently(
    fake_garmin_client: MagicMock, fake_admin_client: MagicMock
) -> None:
    """A non-fatal (non-429/non-401) activities failure must be swallowed
    so the per-day loop still runs.

    Covers sync.py lines 64-65 (the generic Exception catch in activities)."""
    fake_garmin_client.get_activities_by_date.side_effect = RuntimeError("activities 500")

    with patch("garmin_sync.sync.get_admin_client", return_value=fake_admin_client):
        sync_user_for_date_range(
            user_id="u1",
            client=fake_garmin_client,
            start=date(2026, 5, 15),
            end=date(2026, 5, 15),
        )

    tables_touched = {call.args[0] for call in fake_admin_client.table.call_args_list}
    assert "activities" not in tables_touched
    # But the per-day loop still ran
    assert "daily_metrics" in tables_touched
