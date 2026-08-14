"""Tests for the Body Battery backfill script (issue #170)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from garmin_sync.coach.backfill_body_battery import backfill_body_battery


def _row(
    *,
    user_id: str = "u1",
    day: str = "2026-08-14",
    high: int | None,
    current: int | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": day,
        "body_battery_high": high,
        "body_battery_low": 26,
        "body_battery_current": current,
        "raw": raw
        if raw is not None
        else {
            "calendarDate": day,
            "bodyBatteryHighestValue": 95,
            "bodyBatteryLowestValue": 26,
            "bodyBatteryMostRecentValue": 26,
        },
    }


def _fake_db(rows: list[dict[str, Any]]) -> tuple[MagicMock, MagicMock]:
    """Return (db, update_mock) — update_mock records the payloads written."""
    update_mock = MagicMock()
    table = MagicMock()
    table.select.return_value.execute.return_value.data = rows

    def _update(payload: dict[str, Any]) -> MagicMock:
        update_mock(payload)
        return MagicMock()

    table.update.side_effect = _update
    db = MagicMock()
    db.table.return_value = table
    return db, update_mock


def _patch(monkeypatch: Any, rows: list[dict[str, Any]]) -> tuple[MagicMock, MagicMock]:
    from garmin_sync.coach import backfill_body_battery as mod

    db, update_mock = _fake_db(rows)
    baselines = MagicMock()
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "recompute_recovery_baselines", baselines)
    return update_mock, baselines


def test_backfill_no_rows_returns_zero_counts(monkeypatch: Any) -> None:
    update_mock, baselines = _patch(monkeypatch, [])
    out = backfill_body_battery()
    assert out == {"updated": 0, "skipped": 0, "errors": 0, "users_recomputed": 0}
    update_mock.assert_not_called()
    baselines.assert_not_called()


def test_backfill_rewrites_high_from_raw_and_fills_current(monkeypatch: Any) -> None:
    update_mock, baselines = _patch(monkeypatch, [_row(high=26)])
    out = backfill_body_battery()
    assert out["updated"] == 1
    assert out["skipped"] == 0
    assert out["users_recomputed"] == 1
    update_mock.assert_called_once_with({"body_battery_high": 95, "body_battery_current": 26})
    baselines.assert_called_once_with("u1")


def test_backfill_is_idempotent_on_already_correct_rows(monkeypatch: Any) -> None:
    update_mock, baselines = _patch(monkeypatch, [_row(high=95, current=26)])
    out = backfill_body_battery()
    assert out == {"updated": 0, "skipped": 1, "errors": 0, "users_recomputed": 0}
    update_mock.assert_not_called()
    baselines.assert_not_called()


def test_backfill_skips_rows_whose_raw_has_no_body_battery(monkeypatch: Any) -> None:
    update_mock, _ = _patch(monkeypatch, [_row(high=26, raw={"calendarDate": "2026-08-14"})])
    out = backfill_body_battery()
    assert out["updated"] == 0
    assert out["skipped"] == 1
    update_mock.assert_not_called()


def test_dry_run_reports_what_would_change_without_writing(monkeypatch: Any) -> None:
    update_mock, baselines = _patch(monkeypatch, [_row(high=26)])
    out = backfill_body_battery(dry_run=True)
    assert out["updated"] == 1
    update_mock.assert_not_called()
    baselines.assert_not_called()


def test_baselines_recomputed_once_per_touched_user(monkeypatch: Any) -> None:
    rows = [
        _row(user_id="u1", day="2026-08-13", high=26),
        _row(user_id="u1", day="2026-08-14", high=26),
        _row(user_id="u2", day="2026-08-14", high=95, current=26),
    ]
    _, baselines = _patch(monkeypatch, rows)
    out = backfill_body_battery()
    assert out["updated"] == 2
    assert out["users_recomputed"] == 1
    baselines.assert_called_once_with("u1")


def test_skip_baselines_leaves_recovery_baselines_untouched(monkeypatch: Any) -> None:
    _, baselines = _patch(monkeypatch, [_row(high=26)])
    out = backfill_body_battery(recompute_baselines=False)
    assert out["updated"] == 1
    assert out["users_recomputed"] == 0
    baselines.assert_not_called()


def test_row_failure_is_counted_and_does_not_abort_the_run(monkeypatch: Any) -> None:
    from garmin_sync.coach import backfill_body_battery as mod

    rows = [_row(day="2026-08-13", high=26), _row(day="2026-08-14", high=26)]
    db, _ = _fake_db(rows)
    calls = {"n": 0}

    def _boom(payload: dict[str, Any]) -> MagicMock:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("network")
        return MagicMock()

    db.table.return_value.update.side_effect = _boom
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(mod, "recompute_recovery_baselines", MagicMock())
    out = backfill_body_battery()
    assert out["errors"] == 1
    assert out["updated"] == 1


def test_baseline_failure_is_counted_as_an_error(monkeypatch: Any) -> None:
    from garmin_sync.coach import backfill_body_battery as mod

    db, _ = _fake_db([_row(high=26)])
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)
    monkeypatch.setattr(
        mod, "recompute_recovery_baselines", MagicMock(side_effect=RuntimeError("boom"))
    )
    out = backfill_body_battery()
    assert out["errors"] == 1
    assert out["users_recomputed"] == 0


def test_backfill_skips_rows_whose_raw_is_not_a_payload(monkeypatch: Any) -> None:
    """Defensive: a row whose `raw` is not an object cannot be re-derived."""
    broken = {**_row(high=26), "raw": None}
    update_mock, _ = _patch(monkeypatch, [broken])
    out = backfill_body_battery()
    assert out["skipped"] == 1
    update_mock.assert_not_called()
