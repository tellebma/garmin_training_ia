"""Tests for coach.cron.run_weekly_cron — freshness guard before plan regeneration.

Regression coverage for #126: a user whose Garmin sync has been dead for weeks
must NOT get a plan regenerated on stale data, and must trigger exactly one
alert so the failure stops being silent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from garmin_sync.coach.cron import GARMIN_SYNC_STALE_DAYS


def _fake_db(
    *, race_rows: list[dict[str, object]], creds_rows: list[dict[str, object]]
) -> MagicMock:
    fake_db = MagicMock()

    def table(name: str) -> MagicMock:
        m = MagicMock()
        if name == "race_goals":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = (
                race_rows
            )
        elif name == "garmin_credentials":
            m.select.return_value.in_.return_value.execute.return_value.data = creds_rows
        return m

    fake_db.table.side_effect = table
    return fake_db


def _iso(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def test_run_weekly_cron_skips_regeneration_and_alerts_when_sync_is_stale() -> None:
    """garmin_synced beyond GARMIN_SYNC_STALE_DAYS -> no generate_plan call,
    result flagged stale_data_skipped, exactly one alert fired."""
    from garmin_sync.coach.cron import run_weekly_cron

    stale_days = GARMIN_SYNC_STALE_DAYS + 16  # matches the 19j prod incident
    fake_db = _fake_db(
        race_rows=[{"user_id": "u-stale"}],
        creds_rows=[{"user_id": "u-stale", "last_activities_sync_at": _iso(stale_days)}],
    )

    with (
        patch("garmin_sync.coach.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.coach.cron.generate_plan") as generate_plan_mock,
        patch("garmin_sync.coach.cron.ensure_sessions") as ensure_sessions_mock,
        patch("garmin_sync.coach.cron.capture") as capture_mock,
    ):
        result = run_weekly_cron()

    generate_plan_mock.assert_not_called()
    ensure_sessions_mock.assert_not_called()
    capture_mock.assert_called_once()
    assert capture_mock.call_args.kwargs["user_id"] == "u-stale"

    assert result["results"]["u-stale"]["status"] == "stale_data_skipped"
    assert result["results"]["u-stale"]["days_since_sync"] >= GARMIN_SYNC_STALE_DAYS + 1
    assert result["skipped_stale"] == 1


def test_run_weekly_cron_regenerates_when_sync_is_fresh() -> None:
    """A recently synced user still gets a plan regenerated as before, no alert."""
    from garmin_sync.coach.cron import run_weekly_cron

    fake_db = _fake_db(
        race_rows=[{"user_id": "u-fresh"}],
        creds_rows=[{"user_id": "u-fresh", "last_activities_sync_at": _iso(1)}],
    )

    with (
        patch("garmin_sync.coach.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.coach.cron.generate_plan", return_value={"status": "ok"}) as gen_mock,
        patch(
            "garmin_sync.coach.cron.ensure_sessions", return_value={"status": "ok"}
        ) as ensure_mock,
        patch("garmin_sync.coach.cron.capture") as capture_mock,
    ):
        result = run_weekly_cron()

    gen_mock.assert_called_once_with("u-fresh")
    ensure_mock.assert_called_once_with(user_id="u-fresh")
    capture_mock.assert_not_called()
    assert result["results"]["u-fresh"]["status"] == "ok"
    assert result["skipped_stale"] == 0


def test_run_weekly_cron_does_not_block_users_with_no_sync_history_yet() -> None:
    """No garmin_credentials row at all (never connected) is 'no_data', distinct
    from 'stale' — must not be blocked by this guard (separate onboarding concern)."""
    from garmin_sync.coach.cron import run_weekly_cron

    fake_db = _fake_db(race_rows=[{"user_id": "u-new"}], creds_rows=[])

    with (
        patch("garmin_sync.coach.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.coach.cron.generate_plan", return_value={"status": "ok"}) as gen_mock,
        patch("garmin_sync.coach.cron.ensure_sessions", return_value={"status": "ok"}),
        patch("garmin_sync.coach.cron.capture") as capture_mock,
    ):
        result = run_weekly_cron()

    gen_mock.assert_called_once_with("u-new")
    capture_mock.assert_not_called()
    assert result["results"]["u-new"]["status"] == "ok"


def test_run_weekly_cron_handles_no_users() -> None:
    from garmin_sync.coach.cron import run_weekly_cron

    fake_db = _fake_db(race_rows=[], creds_rows=[])

    with (
        patch("garmin_sync.coach.cron.get_admin_client", return_value=fake_db),
        patch("garmin_sync.coach.cron.generate_plan") as gen_mock,
    ):
        result = run_weekly_cron()

    assert result == {"total_users": 0, "skipped_stale": 0, "results": {}}
    gen_mock.assert_not_called()
