from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync import cron


def _patch_recompute_stack(monkeypatch: Any) -> dict[str, MagicMock]:
    mocks = {
        "daily_state": MagicMock(),
        "recovery": MagicMock(),
        "home": MagicMock(return_value=(45.0, 6.0)),
        "overpass": MagicMock(),
        "matching": MagicMock(),
    }
    monkeypatch.setattr(cron, "recompute_daily_state", mocks["daily_state"])
    monkeypatch.setattr(
        "garmin_sync.coach.recovery_baselines.recompute_recovery_baselines", mocks["recovery"]
    )
    monkeypatch.setattr("garmin_sync.coach.home_location.compute_home_location", mocks["home"])
    monkeypatch.setattr("garmin_sync.coach.overpass.refresh_nearby_cols", mocks["overpass"])
    monkeypatch.setattr("garmin_sync.coach.col_matching.recompute_col_crossings", mocks["matching"])
    return mocks


def test_post_sync_recomputes_calls_cols_pipeline_when_home_found(monkeypatch: Any) -> None:
    mocks = _patch_recompute_stack(monkeypatch)

    cron._run_post_sync_recomputes("user-1", mode=cron.SYNC_MODE_FULL)

    mocks["home"].assert_called_once_with("user-1")
    mocks["overpass"].assert_called_once_with("user-1", 45.0, 6.0)
    mocks["matching"].assert_called_once_with("user-1")
    mocks["daily_state"].assert_called_once()
    mocks["recovery"].assert_called_once_with("user-1")


def test_post_sync_recomputes_without_home_skips_overpass_but_still_matches(
    monkeypatch: Any,
) -> None:
    mocks = _patch_recompute_stack(monkeypatch)
    mocks["home"].return_value = None
    monkeypatch.setattr("garmin_sync.coach.home_location.compute_home_location", mocks["home"])

    cron._run_post_sync_recomputes("user-1", mode=cron.SYNC_MODE_ACTIVITIES_ONLY)

    mocks["overpass"].assert_not_called()
    # Le matching par bbox d'activité ne dépend plus du domicile.
    mocks["matching"].assert_called_once_with("user-1")


def test_post_sync_recomputes_sleep_mode_skips_activity_dependent_work(
    monkeypatch: Any,
) -> None:
    # Audit 2026-07-26 : le cron sommeil de 08:00 ne change aucune activité —
    # rejouer Banister 180j, le domicile et le matching cols à ce moment-là est
    # du travail pur perdu (~5-8 requêtes + 181 lignes écrites par user par run).
    # Seules les baselines de récupération dépendent des données de sommeil.
    mocks = _patch_recompute_stack(monkeypatch)

    cron._run_post_sync_recomputes("user-1", mode=cron.SYNC_MODE_SLEEP_ONLY)

    mocks["recovery"].assert_called_once_with("user-1")
    mocks["daily_state"].assert_not_called()
    mocks["home"].assert_not_called()
    mocks["overpass"].assert_not_called()
    mocks["matching"].assert_not_called()


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
    cron._run_post_sync_recomputes("user-1", mode=cron.SYNC_MODE_FULL)
