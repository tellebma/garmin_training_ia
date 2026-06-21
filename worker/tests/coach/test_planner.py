"""Tests for the plan orchestrator (generate_plan)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from garmin_sync.coach.activity_review import build_activity_review
from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    TAPER_RAMP_RATE,
    compute_first_week_tss_multiplier,
    distribute_weekly_tss_by_sport,
    generate_plan,
    pick_session_types_for_phase,
)


def test_weak_sport_gets_more_volume_than_strong_continuous() -> None:
    out = distribute_weekly_tss_by_sport(
        weekly_tss=300,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 1, "bike": 5, "run": 3},
    )
    assert round(sum(out.values()), 1) == 300.0
    assert out["swim"] > out["run"] > out["bike"]


def test_level_2_and_1_differ() -> None:
    a = distribute_weekly_tss_by_sport(
        weekly_tss=200, sports_in_race=["swim", "bike"], sports_strengths={"swim": 1, "bike": 3}
    )
    b = distribute_weekly_tss_by_sport(
        weekly_tss=200, sports_in_race=["swim", "bike"], sports_strengths={"swim": 2, "bike": 3}
    )
    assert a["swim"] > b["swim"]


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


def test_first_week_multiplier_keeps_normal_load_without_risk() -> None:
    review = build_activity_review([], today=date(2026, 5, 20))
    assert compute_first_week_tss_multiplier(review) == 1.0


def test_first_week_multiplier_deloads_on_recent_load_spike() -> None:
    review = build_activity_review(
        [
            {"start_time": "2026-05-19T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 95},
            {
                "start_time": "2026-05-18T08:00:00Z",
                "sport": "bike",
                "duration_s": 3 * 3600,
                "tss": 130,
            },
            {"start_time": "2026-05-08T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 80},
            {"start_time": "2026-05-01T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 80},
            {"start_time": "2026-04-24T08:00:00Z", "sport": "run", "duration_s": 3600, "tss": 80},
        ],
        today=date(2026, 5, 20),
    )

    assert compute_first_week_tss_multiplier(review) == 0.85


def test_first_week_multiplier_light_deload_on_recent_long_session() -> None:
    review = build_activity_review(
        [
            {
                "start_time": "2026-05-19T08:00:00Z",
                "sport": "bike",
                "duration_s": 3 * 3600,
                "tss": 95,
            }
        ],
        today=date(2026, 5, 20),
    )

    assert compute_first_week_tss_multiplier(review) == 0.92


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


def test_build_week_sessions_long_session_gets_more_tss_and_duration() -> None:
    """A 'long' session should receive more TSS (and more duration) than 'endurance'."""
    from garmin_sync.coach.planner import _build_week_sessions  # type: ignore[attr-defined]

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # 6 available days, weekly_tss = 420 (= 8h/wk * 50 / 7 * 7 * ramp 1.05 = ~420)
    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=week_start,
        weekly_tss=420.0,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        is_last_week=False,
        race_date=today + timedelta(days=365),
        race_sport="run",
    )

    # Sunday gets the 'long' session (per _placement_priority_for_day)
    long_sessions = [s for s in sessions if s["session_type"] == "long"]
    endurance_sessions = [s for s in sessions if s["session_type"] == "endurance"]
    assert len(long_sessions) >= 1
    assert len(endurance_sessions) >= 1

    # Long must be heavier than endurance in TSS (within same sport)
    max_long_tss = max(s["target_tss"] for s in long_sessions)
    max_endurance_tss = max(s["target_tss"] for s in endurance_sessions)
    assert max_long_tss > max_endurance_tss


def test_build_week_sessions_bike_takes_longer_than_run_at_same_tss() -> None:
    """For the same TSS, bike duration must exceed run duration (different TSS/h)."""
    from garmin_sync.coach.planner import _training_day_session

    used: list[str] = []
    bike_session = _training_day_session(
        day=date.today(),
        day_idx=1,
        phase="base",
        week_offset=0,
        types_for_phase=["endurance"],
        sports_in_race=["bike"],
        tss_by_sport={"bike": 50.0},
        used_types=used,
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    used2: list[str] = []
    run_session = _training_day_session(
        day=date.today(),
        day_idx=1,
        phase="base",
        week_offset=0,
        types_for_phase=["endurance"],
        sports_in_race=["run"],
        tss_by_sport={"run": 50.0},
        used_types=used2,
        sport_weight_total={"run": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    assert bike_session["target_tss"] == run_session["target_tss"]  # same TSS
    assert bike_session["target_duration_s"] > run_session["target_duration_s"]


def test_compute_elevation_per_sport_sums_legs() -> None:
    from garmin_sync.coach.planner import compute_elevation_per_sport

    legs = [
        {"discipline": "swim", "elevation_gain_m": 0},
        {"discipline": "bike", "elevation_gain_m": 2200},
        {"discipline": "run", "elevation_gain_m": 200},
    ]
    out = compute_elevation_per_sport(legs)
    assert out == {"swim": 0, "bike": 2200, "run": 200}


def test_compute_weekly_elevation_targets_respects_thresholds() -> None:
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    # Hilly tri: bike 2200, run 200 -> both above threshold (>=300 / >=100)
    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"swim": 0, "bike": 2200, "run": 200}, weeks_count=13
    )
    assert out["bike"] == 2200 // 13
    assert out["run"] == 200 // 13
    assert out["swim"] == 0


def test_compute_weekly_elevation_targets_zero_on_flat_race() -> None:
    """A flat 10K route race -> all sports below threshold -> no hill training."""
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    out = compute_weekly_elevation_targets(race_dplus_by_sport={"run": 50}, weeks_count=12)
    assert out == {"run": 0}


def test_build_week_sessions_long_session_gets_more_elevation() -> None:
    """Hilly race: long bike must receive > endurance bike D+ target."""
    from garmin_sync.coach.planner import _build_week_sessions

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=week_start,
        weekly_tss=420.0,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        is_last_week=False,
        race_date=today + timedelta(days=365),
        race_sport="run",
        weekly_elevation_by_sport={"swim": 0, "bike": 200, "run": 30},
    )

    bike_sessions = [s for s in sessions if s["sport"] == "bike"]
    long_bike = [s for s in bike_sessions if s["session_type"] == "long"]
    endurance_bike = [s for s in bike_sessions if s["session_type"] == "endurance"]
    # Swim sessions never get a D+ target
    swim_sessions = [s for s in sessions if s["sport"] == "swim"]
    if long_bike and endurance_bike:
        assert (
            long_bike[0]["target_elevation_gain_m"] >= endurance_bike[0]["target_elevation_gain_m"]
        )
    # Swim D+ target is None or 0
    for s in swim_sessions:
        assert not s.get("target_elevation_gain_m")


def test_build_week_sessions_weekly_tss_sums_close_to_budget() -> None:
    """The sum of session TSS across the week should land within ~5% of weekly_tss."""
    from garmin_sync.coach.planner import _build_week_sessions

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=week_start,
        weekly_tss=420.0,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        is_last_week=False,
        race_date=today + timedelta(days=365),
        race_sport="run",
    )
    total = sum(s["target_tss"] or 0 for s in sessions)
    # Allow ±5% rounding slack from session-weight normalization
    assert 399 <= total <= 441, f"expected ~420 TSS, got {total}"


def test_generate_plan_archives_previous_active_plan(monkeypatch) -> None:
    """Re-generating archives previous plans AND deletes their planned_sessions
    before inserting the new plan (prevents duplicate sessions on /today)."""
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

    # Stable singletons so we can assert against the same mock across calls
    tp_mock = MagicMock()
    tp_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "old-plan-1"}
    ]
    tp_mock.update.return_value.in_.return_value.execute.return_value = MagicMock()
    tp_mock.insert.return_value.execute.return_value.data = [{"id": "plan-2"}]

    ps_mock = MagicMock()
    ps_mock.delete.return_value.in_.return_value.execute.return_value = MagicMock()

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
            return tp_mock
        elif table_name == "planned_sessions":
            return ps_mock
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    result = generate_plan("u1")
    assert result["status"] == "ok"

    # 1. planned_sessions of previous plans deleted
    ps_mock.delete.assert_called_once()
    delete_in_args, _ = ps_mock.delete.return_value.in_.call_args
    assert delete_in_args[0] == "plan_id"
    assert delete_in_args[1] == ["old-plan-1"]

    # 2. previous training_plans archived
    tp_mock.update.assert_called_once()
    update_args, _ = tp_mock.update.call_args
    assert update_args[0]["status"] == "archived"
    update_in_args, _ = tp_mock.update.return_value.in_.call_args
    assert update_in_args[0] == "id"
    assert update_in_args[1] == ["old-plan-1"]


def test_beginner_build_has_no_hard_intervals() -> None:
    types = pick_session_types_for_phase("build", max_level=1)
    assert "threshold" not in types
    assert "intervals" not in types
    assert "endurance" in types


def test_level3_build_allows_threshold_not_intervals() -> None:
    types = pick_session_types_for_phase("build", max_level=3)
    assert "threshold" in types
    assert "intervals" not in types


def test_advanced_peak_allows_intervals() -> None:
    types = pick_session_types_for_phase("peak", max_level=5)
    assert "intervals" in types


def test_weekly_tss_floor_scales_with_hours() -> None:
    from garmin_sync.coach.planner import weekly_tss_floor_from_hours

    assert weekly_tss_floor_from_hours(8) == 360
    assert weekly_tss_floor_from_hours(None) == 0
