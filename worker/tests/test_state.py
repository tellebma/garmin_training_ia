"""Tests for coach/state.py — Banister state materialization."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


def _mock_supabase_chain(db, *, profile=None, activities=None):
    """Configure db.table('...').select('...').eq/gte('...').execute() chain."""
    profile_chain = MagicMock()
    profile_chain.select.return_value = profile_chain
    profile_chain.eq.return_value = profile_chain
    profile_chain.single.return_value = profile_chain
    profile_chain.execute.return_value = MagicMock(data=profile or {})

    act_chain = MagicMock()
    act_chain.select.return_value = act_chain
    act_chain.eq.return_value = act_chain
    act_chain.gte.return_value = act_chain
    # E24 : les lectures qui comptent filtrent les activités exclues.
    act_chain.is_.return_value = act_chain
    act_chain.execute.return_value = MagicMock(data=activities or [])

    upsert_chain = MagicMock()
    upsert_chain.upsert.return_value = upsert_chain
    upsert_chain.execute.return_value = MagicMock(data=[])

    def table_fn(name):
        if name == "athlete_profiles":
            return profile_chain
        if name == "activities":
            return act_chain
        if name == "daily_banister_state":
            return upsert_chain
        raise AssertionError(f"Unexpected table: {name}")

    db.table.side_effect = table_fn
    return upsert_chain


def test_recompute_cold_start_no_activities(mock_db):
    """#134: cold start — the profile estimate describes the CURRENT form.

    The baseline must hold at ~35.71 (5 h x 50 / 7) all along the window instead
    of decaying to ~0 before reaching today (the old, planner-divergent behavior).
    """
    from garmin_sync.coach import state as state_module

    upsert = _mock_supabase_chain(
        mock_db,
        profile={"hours_per_week": 5, "ftp_watts": None, "fc_max_bpm": None},
        activities=[],
    )

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        result = state_module.recompute_daily_state("user-1", days_back=180)

    assert result["rows_upserted"] == 181
    upsert.upsert.assert_called_once()
    rows = upsert.upsert.call_args[0][0]
    assert len(rows) == 181
    assert rows[0]["ctl"] == pytest.approx(35.71, abs=0.01)
    assert rows[-1]["ctl"] == pytest.approx(35.71, abs=0.01)
    assert rows[-1]["tsb"] == 0.0


def test_cold_start_state_matches_planner_today_ctl(mock_db):
    """#134 cross-regression: for the same cold-start user, recompute_daily_state
    and the planner's _load_today_banister_state must agree on today's CTL."""
    from garmin_sync.coach import planner as planner_module
    from garmin_sync.coach import state as state_module

    profile = {"hours_per_week": 4, "ftp_watts": None, "fc_max_bpm": None}
    upsert = _mock_supabase_chain(mock_db, profile=profile, activities=[])

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        state_module.recompute_daily_state("user-1", days_back=180)
    rows = upsert.upsert.call_args[0][0]

    planner_db = MagicMock()
    chain = planner_db.table.return_value
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    _, today_state, _, _ = planner_module._load_today_banister_state(
        db=planner_db, user_id="user-1", profile=profile, today=date.today()
    )

    assert today_state.ctl == pytest.approx(4 * 50 / 7, abs=0.01)
    assert rows[-1]["ctl"] == pytest.approx(today_state.ctl, abs=0.01)
    assert rows[-1]["tsb"] == pytest.approx(today_state.tsb, abs=0.01)


def test_recompute_uses_observed_hr_max_when_profile_fc_max_null(mock_db):
    """#120: fc_max_bpm NULL in prod → hrTSS via 90-day observed hr_max.

    Two same-duration activities at very different HR must produce different
    daily_tss values (not both duration x 50).
    """
    from garmin_sync.coach import state as state_module

    today = date.today()
    d_easy = today - timedelta(days=3)
    d_hard = today - timedelta(days=2)
    activities = [
        {
            "start_time": f"{d_easy.isoformat()}T08:00:00Z",
            "sport": "run",
            "duration_s": 3600,
            "power_avg": None,
            "hr_avg": 120,
            "hr_max": 150,
        },
        {
            "start_time": f"{d_hard.isoformat()}T08:00:00Z",
            "sport": "run",
            "duration_s": 3600,
            "power_avg": None,
            "hr_avg": 175,
            "hr_max": 188,
        },
    ]
    upsert = _mock_supabase_chain(
        mock_db,
        profile={"hours_per_week": 5, "ftp_watts": None, "fc_max_bpm": None},
        activities=activities,
    )

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        state_module.recompute_daily_state("user-1", days_back=30)

    rows = upsert.upsert.call_args[0][0]
    by_date = {r["date"]: r["daily_tss"] for r in rows}
    tss_easy = by_date[d_easy.isoformat()]
    tss_hard = by_date[d_hard.isoformat()]
    assert tss_easy is not None
    assert tss_hard is not None
    assert tss_hard > tss_easy


def test_recompute_converges_with_regular_tss(mock_db):
    """30 days, 5 days/week x 50 TSS = 250 TSS/week. CTL converges around 35 (250/7)."""
    from garmin_sync.coach import state as state_module

    today = date.today()
    activities = []
    for offset in range(30):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        activities.append(
            {
                "start_time": f"{d.isoformat()}T08:00:00Z",
                "sport": "bike",
                "duration_s": 3600,
                "power_avg": 200,
                "hr_avg": 140,
            }
        )

    upsert = _mock_supabase_chain(
        mock_db,
        profile={"hours_per_week": 5, "ftp_watts": 250, "fc_max_bpm": 180},
        activities=activities,
    )

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        result = state_module.recompute_daily_state("user-1", days_back=30)

    assert result["rows_upserted"] == 31
    rows = upsert.upsert.call_args[0][0]
    last_ctl = rows[-1]["ctl"]
    assert 15.0 < last_ctl < 50.0


def test_recompute_handles_missing_profile(mock_db):
    """No profile row → use defaults (0.0 initial CTL/ATL), no crash."""
    from garmin_sync.coach import state as state_module

    upsert = _mock_supabase_chain(mock_db, profile=None, activities=[])

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        result = state_module.recompute_daily_state("user-1", days_back=14)

    assert result["rows_upserted"] == 15
    rows = upsert.upsert.call_args[0][0]
    assert rows[0]["ctl"] == 0.0


def test_recompute_single_day_days_back_zero(mock_db):
    """days_back=0 → 1 row (today), should still call upsert."""
    from garmin_sync.coach import state as state_module

    upsert = _mock_supabase_chain(mock_db, profile={"hours_per_week": None}, activities=[])

    with patch.object(state_module, "get_admin_client", return_value=mock_db):
        result = state_module.recompute_daily_state("user-1", days_back=0)

    assert result["rows_upserted"] == 1
    upsert.upsert.assert_called_once()
