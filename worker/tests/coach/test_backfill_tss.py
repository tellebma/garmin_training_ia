"""Tests for the TSS backfill script."""

from __future__ import annotations

from unittest.mock import MagicMock

from garmin_sync.coach.backfill_tss import backfill_tss


def test_backfill_no_activities_returns_zero_counts(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = []
    monkeypatch.setattr(mod, "get_admin_client", lambda: fake_db)
    out = backfill_tss()
    assert out == {"updated": 0, "skipped": 0, "errors": 0}


def test_backfill_updates_each_activity_with_tss(monkeypatch) -> None:
    from garmin_sync.coach import backfill_tss as mod

    activities_data = [
        {
            "id": "a1",
            "user_id": "u1",
            "duration_s": 3600,
            "sport": "running",
            "power_avg": None,
            "hr_avg": 153,
        },
        {
            "id": "a2",
            "user_id": "u1",
            "duration_s": 7200,
            "sport": "cycling",
            "power_avg": 200,
            "hr_avg": None,
        },
    ]
    profile_data = {"ftp_watts": 250, "fc_max_bpm": 170}

    def _table_router(name: str):
        m = MagicMock()
        if name == "activities":
            m.select.return_value.is_.return_value.execute.return_value.data = activities_data
            m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value
            chain.execute.return_value.data = profile_data
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(mod, "get_admin_client", lambda: fake_db)

    out = backfill_tss()
    assert out["updated"] == 2
    assert out["errors"] == 0
