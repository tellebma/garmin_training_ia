"""Tests for the TSS backfill script."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from garmin_sync.coach.backfill_tss import backfill_tss


def _recent(days_ago: int) -> str:
    return f"{(date.today() - timedelta(days=days_ago)).isoformat()}T08:00:00Z"


def _fake_db(activities_data, profile_data):
    tables: dict[str, MagicMock] = {}

    def _table_router(name: str):
        if name in tables:
            return tables[name]
        m = MagicMock()
        if name == "activities":
            sel = m.select.return_value
            sel.is_.return_value.execute.return_value.data = activities_data
            sel.execute.return_value.data = activities_data
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value
            chain.execute.return_value.data = profile_data
        tables[name] = m
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    return fake_db


def test_backfill_no_activities_returns_zero_counts(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    recompute = MagicMock()
    monkeypatch.setattr(mod, "recompute_daily_state", recompute)
    monkeypatch.setattr(mod, "get_admin_client", lambda: _fake_db([], {}))
    out = backfill_tss()
    assert out == {"updated": 0, "skipped": 0, "errors": 0, "users_recomputed": 0}
    recompute.assert_not_called()


def test_backfill_updates_each_activity_with_tss(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {
            "id": "a1",
            "user_id": "u1",
            "start_time": _recent(1),
            "duration_s": 3600,
            "sport": "running",
            "power_avg": None,
            "hr_avg": 153,
            "hr_max": 168,
            "tss": None,
        },
        {
            "id": "a2",
            "user_id": "u1",
            "start_time": _recent(2),
            "duration_s": 7200,
            "sport": "cycling",
            "power_avg": 200,
            "hr_avg": None,
            "hr_max": None,
            "tss": None,
        },
    ]
    profile_data = {"ftp_watts": 250, "fc_max_bpm": 170}

    recompute = MagicMock(return_value={"rows_upserted": 181})
    monkeypatch.setattr(mod, "recompute_daily_state", recompute)
    monkeypatch.setattr(mod, "get_admin_client", lambda: _fake_db(activities_data, profile_data))

    out = backfill_tss()
    assert out["updated"] == 2
    assert out["errors"] == 0
    assert out["users_recomputed"] == 1
    recompute.assert_called_once_with("u1")


def test_backfill_recompute_all_fixes_wrong_stored_tss(monkeypatch) -> None:
    """#120: prod rows all carry duration*50 — recompute_all must rewrite them,
    and leave already-correct rows untouched (idempotent)."""
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {  # stored 50.0 (flat fallback) but hrTSS says 100.0 → must be updated
            "id": "a1",
            "user_id": "u1",
            "start_time": _recent(1),
            "duration_s": 3600,
            "sport": "run",
            "power_avg": None,
            "hr_avg": 153,
            "hr_max": 170,
            "tss": 50.0,
        },
        {  # already correct → skipped
            "id": "a2",
            "user_id": "u1",
            "start_time": _recent(2),
            "duration_s": 3600,
            "sport": "run",
            "power_avg": None,
            "hr_avg": 153,
            "hr_max": 170,
            "tss": 100.0,
        },
    ]
    profile_data = {"ftp_watts": None, "fc_max_bpm": 170}

    recompute = MagicMock(return_value={"rows_upserted": 181})
    monkeypatch.setattr(mod, "recompute_daily_state", recompute)
    monkeypatch.setattr(mod, "get_admin_client", lambda: _fake_db(activities_data, profile_data))

    out = backfill_tss(recompute_all=True)
    assert out["updated"] == 1
    assert out["skipped"] == 1
    assert out["users_recomputed"] == 1


def test_backfill_uses_observed_hr_max_when_profile_fc_max_null(monkeypatch) -> None:
    """#120: fc_max_bpm NULL → fallback on the user's observed hr_max (90 d)."""
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {
            "id": "a1",
            "user_id": "u1",
            "start_time": _recent(1),
            "duration_s": 3600,
            "sport": "run",
            "power_avg": None,
            "hr_avg": 153,
            "hr_max": 170,
            "tss": None,
        },
    ]
    profile_data = {"ftp_watts": None, "fc_max_bpm": None}

    db = _fake_db(activities_data, profile_data)
    monkeypatch.setattr(mod, "recompute_daily_state", MagicMock())
    monkeypatch.setattr(mod, "get_admin_client", lambda: db)

    out = backfill_tss()
    assert out["updated"] == 1
    # fc_max resolved to 170 → LTHR 153 → hrTSS = 100, not the flat 50/h fallback
    activities_table = db.table("activities")
    activities_table.update.assert_called_once_with({"tss": 100.0})


def test_backfill_skip_state_recompute(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {
            "id": "a1",
            "user_id": "u1",
            "start_time": _recent(1),
            "duration_s": 3600,
            "sport": "run",
            "power_avg": None,
            "hr_avg": 153,
            "hr_max": 170,
            "tss": None,
        },
    ]
    recompute = MagicMock()
    monkeypatch.setattr(mod, "recompute_daily_state", recompute)
    monkeypatch.setattr(
        mod, "get_admin_client", lambda: _fake_db(activities_data, {"fc_max_bpm": 170})
    )

    out = backfill_tss(recompute_state=False)
    assert out["updated"] == 1
    assert out["users_recomputed"] == 0
    recompute.assert_not_called()
