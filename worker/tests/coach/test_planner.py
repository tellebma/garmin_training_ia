"""Tests for the plan orchestrator (generate_plan)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    TAPER_RAMP_RATE,
    distribute_weekly_tss_by_sport,
    generate_plan,
    pick_session_types_for_phase,
)


def test_distribute_weekly_tss_no_sports_strengths_returns_equal_share() -> None:
    """Triathlon with sports_strengths all=3 -> equal share between swim/bike/run."""
    sports_in_race = ["swim", "bike", "run"]
    strengths = {"swim": 3, "bike": 3, "run": 3}
    out = distribute_weekly_tss_by_sport(
        weekly_tss=300, sports_in_race=sports_in_race, sports_strengths=strengths
    )
    assert abs(out["swim"] - 100) < 1
    assert abs(out["bike"] - 100) < 1
    assert abs(out["run"] - 100) < 1


def test_distribute_weekly_tss_weak_sport_gets_more() -> None:
    """sports_strengths.swim=1 -> swim gets more share; bike=5 -> less; normalised."""
    sports_in_race = ["swim", "bike", "run"]
    strengths = {"swim": 1, "bike": 5, "run": 3}
    out = distribute_weekly_tss_by_sport(
        weekly_tss=300, sports_in_race=sports_in_race, sports_strengths=strengths
    )
    assert out["swim"] > out["run"] > out["bike"]
    assert abs(sum(out.values()) - 300) < 0.5


def test_pick_session_types_for_base_phase() -> None:
    types = pick_session_types_for_phase("base")
    assert "endurance" in types
    assert "long" in types
    assert "recovery" in types


def test_pick_session_types_for_build_phase() -> None:
    types = pick_session_types_for_phase("build")
    assert "threshold" in types
    assert "long" in types
    assert "endurance" in types


def test_pick_session_types_for_peak_phase() -> None:
    types = pick_session_types_for_phase("peak")
    assert "intervals" in types


def test_pick_session_types_for_taper_phase() -> None:
    types = pick_session_types_for_phase("taper")
    assert "endurance" in types
    assert "long" not in types


def test_ramp_rates_consistent_with_spec() -> None:
    """Sanity check : deload < normal, taper << normal."""
    assert DELOAD_RAMP_RATE < NORMAL_RAMP_RATE
    assert TAPER_RAMP_RATE < DELOAD_RAMP_RATE


def test_generate_plan_no_race_goal_returns_error(monkeypatch) -> None:
    """Without an active race_goal, generate_plan returns no_race_goal status."""
    from garmin_sync.coach import planner as p_mod

    fake_db = MagicMock()
    profile_chain = fake_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value  # noqa: E501
    profile_chain.data = {
        "user_id": "u1",
        "hours_per_week": 6,
        "ftp_watts": None,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    race_chain = fake_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501
    race_chain.data = None

    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)
    result = generate_plan("u1")
    assert result["status"] == "no_race_goal"


def test_generate_plan_happy_path_writes_to_db(monkeypatch) -> None:
    """generate_plan with profile + race_goal inserts training_plans + planned_sessions."""
    from garmin_sync.coach import planner as p_mod

    profile = {
        "user_id": "u1",
        "hours_per_week": 6,
        "ftp_watts": 200,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    race = {
        "id": "rg-1",
        "race_date": (date.today() + timedelta(weeks=8)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 53, "elevation_gain_m": 2200},
            {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
        ],
    }

    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value.execute.return_value
            chain.data = profile
        elif table_name == "race_goals":
            chain = m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501
            chain.data = race
        elif table_name == "activities":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            m.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
        elif table_name == "planned_sessions":
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u1")
    assert result["status"] == "ok"
    assert result["weeks_count"] == 8
    assert result["sessions_count"] > 0


def test_generate_plan_cold_start_uses_profile_estimate_directly(monkeypatch) -> None:
    """Cold start (no activities) must NOT decay init_ctl over 180 days.

    Regression for the bug where ctl_initial dropped to ~10 for an 8h/wk athlete
    because compute_banister_history simulated 180 days of zero TSS starting
    from init_ctl=57, ending at ~57*exp(-180/42) ≈ 0.79.
    """
    from garmin_sync.coach import planner as p_mod

    profile = {
        "user_id": "u-cold",
        "hours_per_week": 8,
        "ftp_watts": None,
        "fc_max_bpm": 185,
        "sports_strengths": {"swim": 2, "bike": 3, "run": 1},
        "available_days": ["tue", "wed", "thu", "sat", "fri", "sun"],
    }
    race = {
        "id": "rg-cold",
        "race_date": (date.today() + timedelta(weeks=13)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 53, "elevation_gain_m": 2200},
            {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
        ],
    }
    inserted_plan: dict[str, object] = {}

    def _capture_insert(payload):
        inserted_plan.update(payload)
        m = MagicMock()
        m.execute.return_value.data = [{"id": "plan-cold"}]
        return m

    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value.execute.return_value
            chain.data = profile
        elif table_name == "race_goals":
            chain = m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501
            chain.data = race
        elif table_name == "activities":
            # 0 activities → cold start
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            m.insert.side_effect = _capture_insert
        elif table_name == "planned_sessions":
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u-cold")
    assert result["status"] == "ok"
    # 8h/wk x 50 TSS/h / 7 = 57.14 -- anything < 30 means decay happened (bug)
    assert inserted_plan["ctl_initial"] >= 50, (
        f"cold-start CTL dropped to {inserted_plan['ctl_initial']} (expected ~57)"
    )
    assert inserted_plan["params"]["cold_start"] is True


def test_generate_plan_archives_previous_active_plan(monkeypatch) -> None:
    """Re-generating archives the existing active plan via UPDATE before INSERT."""
    from garmin_sync.coach import planner as p_mod

    profile = {
        "user_id": "u1",
        "hours_per_week": 6,
        "ftp_watts": None,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    race = {
        "id": "rg-1",
        "race_date": (date.today() + timedelta(weeks=8)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
            {"order": 2, "discipline": "bike", "distance_km": 53, "elevation_gain_m": 2200},
            {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
        ],
    }
    update_call = MagicMock()

    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value.execute.return_value
            chain.data = profile
        elif table_name == "race_goals":
            chain = m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501
            chain.data = race
        elif table_name == "activities":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            m.update = update_call
            update_call.return_value.eq.return_value.eq.return_value.execute.return_value = (
                MagicMock()
            )
            m.insert.return_value.execute.return_value.data = [{"id": "plan-2"}]
        else:
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u1")
    assert result["status"] == "ok"
    update_call.assert_called_once()
    args, _kwargs = update_call.call_args
    assert args[0]["status"] == "archived"
