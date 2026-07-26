from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync import cron


def test_post_sync_recomputes_calls_cols_pipeline_when_home_found(monkeypatch: Any) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    recovery_mock = MagicMock()
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", recovery_mock
    )
    home_mock = MagicMock(return_value=(45.0, 6.0))
    monkeypatch.setattr("garmin_sync.coach.home_location.compute_home_location", home_mock)
    overpass_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.overpass.refresh_nearby_cols", overpass_mock)
    matching_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.col_matching.recompute_col_crossings", matching_mock)

    cron._run_post_sync_recomputes("user-1")

    home_mock.assert_called_once_with("user-1")
    overpass_mock.assert_called_once_with("user-1", 45.0, 6.0)
    matching_mock.assert_called_once_with("user-1")


def test_post_sync_recomputes_without_home_skips_overpass_but_still_matches(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", MagicMock()
    )
    monkeypatch.setattr(
        "garmin_sync.coach.home_location.compute_home_location", MagicMock(return_value=None)
    )
    overpass_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.overpass.refresh_nearby_cols", overpass_mock)
    matching_mock = MagicMock()
    monkeypatch.setattr("garmin_sync.coach.col_matching.recompute_col_crossings", matching_mock)

    cron._run_post_sync_recomputes("user-1")

    overpass_mock.assert_not_called()
    # Le matching par bbox d'activité ne dépend plus du domicile.
    matching_mock.assert_called_once_with("user-1")


def test_post_sync_recomputes_swallows_cols_pipeline_errors(monkeypatch: Any) -> None:
    monkeypatch.setattr(cron, "recompute_daily_state", MagicMock())
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", MagicMock()
    )
    monkeypatch.setattr(
        "garmin_sync.coach.home_location.compute_home_location",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    # Must not raise.
    cron._run_post_sync_recomputes("user-1")
