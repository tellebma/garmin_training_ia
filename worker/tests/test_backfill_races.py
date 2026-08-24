"""Tests du backfill du tag course (E23.1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from garmin_sync.coach.backfill_races import backfill_races


def test_backfill_runs_once_per_user_with_a_race() -> None:
    db = MagicMock()
    db.table.return_value.select.return_value.execute.return_value.data = [
        {"user_id": "user-a"},
        {"user_id": "user-b"},
        {"user_id": "user-a"},
    ]

    with (
        patch("garmin_sync.coach.backfill_races.get_admin_client", return_value=db),
        patch("garmin_sync.coach.backfill_races.tag_races_for_user", return_value=2) as tag,
    ):
        result = backfill_races()

    assert result == {"users": 2, "tagged": 4}
    assert [call.args[1] for call in tag.call_args_list] == ["user-a", "user-b"]


def test_backfill_can_target_a_single_user() -> None:
    db = MagicMock()

    with (
        patch("garmin_sync.coach.backfill_races.get_admin_client", return_value=db),
        patch("garmin_sync.coach.backfill_races.tag_races_for_user", return_value=0) as tag,
    ):
        result = backfill_races("user-a")

    assert result == {"users": 1, "tagged": 0}
    tag.assert_called_once_with(db, "user-a")
    db.table.assert_not_called()
