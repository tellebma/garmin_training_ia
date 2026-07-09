"""Tests for the plan orchestrator (generate_plan)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from garmin_sync.coach.activity_review import build_activity_review
from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    TAPER_RAMP_RATE,
    _pick_session_type,
    _progress_for_offset,
    cap_weekly_ramp_by_sport,
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


def test_progress_zero_is_more_balanced_than_progress_one() -> None:
    # swim faible (1), bike fort (5). À progress faible le biais est moindre
    # -> part swim plus proche de l'équilibre ; à progress=1 le biais est plein.
    early = distribute_weekly_tss_by_sport(
        weekly_tss=200,
        sports_in_race=["swim", "bike"],
        sports_strengths={"swim": 1, "bike": 5},
        progress=0.0,
    )
    late = distribute_weekly_tss_by_sport(
        weekly_tss=200,
        sports_in_race=["swim", "bike"],
        sports_strengths={"swim": 1, "bike": 5},
        progress=1.0,
    )
    assert late["swim"] > early["swim"]  # on investit plus sur le faible en fin de build
    assert abs(sum(early.values()) - 200) < 0.01  # toujours normalisé
    assert abs(sum(late.values()) - 200) < 0.01


def test_default_progress_is_backward_compatible() -> None:
    # défaut progress=1.0 -> identique à l'ancien comportement statique.
    out = distribute_weekly_tss_by_sport(
        weekly_tss=300,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 1, "bike": 5, "run": 3},
    )
    # ancien : poids 1.25 / 0.85 / 1.05 -> somme 3.15 ; swim = 300*1.25/3.15
    assert out["swim"] == round(300 * 1.25 / 3.15, 2)


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
    assert "pma" in types
    assert "sprint" in types


def test_pick_session_types_for_taper_phase() -> None:
    types = pick_session_types_for_phase("taper")
    assert "endurance" in types
    assert "long" not in types


def test_pick_session_types_for_build_phase_includes_pma_at_high_level() -> None:
    types = pick_session_types_for_phase("build", max_level=5)
    assert "pma" in types
    assert "threshold" in types


def test_build_phase_excludes_pma_at_level3() -> None:
    types = pick_session_types_for_phase("build", max_level=3)
    assert "pma" not in types
    assert "threshold" in types  # threshold reste accessible dès le niveau 3


def test_peak_phase_excludes_sprint_and_pma_for_low_level() -> None:
    types = pick_session_types_for_phase("peak", max_level=2)
    assert "sprint" not in types
    assert "pma" not in types
    assert "endurance" in types


def test_build_phase_excludes_pma_in_first_half_even_at_high_level() -> None:
    # progress < 0.5 -> 1re moitié de build : pma pas encore introduit, même à
    # un niveau athlète élevé.
    types = pick_session_types_for_phase("build", max_level=5, progress=0.3)
    assert "pma" not in types


def test_build_phase_includes_pma_in_second_half_at_high_level() -> None:
    # progress >= 0.5 -> 2e moitié de build : pma apparaît.
    types = pick_session_types_for_phase("build", max_level=5, progress=0.6)
    assert "pma" in types


def test_build_phase_default_progress_keeps_pma_backward_compatible() -> None:
    # Sans argument progress (défaut 1.0), le comportement existant est
    # inchangé : pma reste présent, comme avant l'introduction du gating.
    types = pick_session_types_for_phase("build", max_level=5)
    assert "pma" in types


def test_pick_session_type_avoids_pma_the_day_after_a_pma_day() -> None:
    # day_idx=1 (mardi) n'est pas un slot réservé (long=dimanche, recovery=lundi/jeudi),
    # donc _pick_session_type applique la logique anti back-to-back hard.
    picked = _pick_session_type(
        day_idx=1, types_for_phase=["pma", "sprint", "endurance"], used_types=["pma"]
    )
    assert picked not in ("pma", "sprint")


def test_pick_session_type_avoids_sprint_the_day_after_a_sprint_day() -> None:
    picked = _pick_session_type(
        day_idx=1, types_for_phase=["pma", "sprint", "endurance"], used_types=["sprint"]
    )
    assert picked not in ("pma", "sprint")


def test_peak_phase_allows_sprint_not_pma_at_level3() -> None:
    types = pick_session_types_for_phase("peak", max_level=3)
    assert "sprint" in types
    assert "pma" not in types


def test_taper_phase_includes_sprint_at_default_level() -> None:
    types = pick_session_types_for_phase("taper")
    assert "sprint" in types
    assert "long" not in types


def test_ramp_rates_consistent_with_spec() -> None:
    """Sanity check : deload < normal, taper << normal."""
    assert DELOAD_RAMP_RATE < NORMAL_RAMP_RATE
    assert TAPER_RAMP_RATE < DELOAD_RAMP_RATE


def test_progress_for_offset_ramps_over_build() -> None:
    phases = [(0, "base"), (1, "base"), (2, "build"), (3, "build"), (4, "peak"), (5, "taper")]
    assert _progress_for_offset(0, phases) == 0.0
    assert _progress_for_offset(3, phases) == 1.0  # dernière semaine de build
    assert _progress_for_offset(5, phases) == 1.0  # tenu en taper (clamp)


def test_progress_for_offset_no_build_uses_last_offset() -> None:
    phases = [(0, "base"), (1, "base"), (2, "taper")]
    assert _progress_for_offset(0, phases) == 0.0
    assert _progress_for_offset(2, phases) == 1.0


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
    # With equal strengths=3, each sport gets an equal share: 420 / 3 = 140.0
    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=week_start,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
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


def test_build_week_sessions_bike_longer_than_run_and_tss_consistent() -> None:
    """Bike endurance clamps up to its realistic floor (>= 90min) while run endurance
    caps lower, so bike runs longer. target_tss is re-derived from the clamped
    duration, so each session stays internally consistent (and the two no longer
    share the same TSS — realistic durations take precedence over the raw budget)."""
    from garmin_sync.coach.planner import _training_day_session, _tss_per_hour

    bike_session = _training_day_session(
        day=date.today(),
        phase="base",
        week_offset=0,
        stype="endurance",
        sport="bike",
        tss_by_sport={"bike": 50.0},
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    run_session = _training_day_session(
        day=date.today(),
        phase="base",
        week_offset=0,
        stype="endurance",
        sport="run",
        tss_by_sport={"run": 50.0},
        sport_weight_total={"run": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    assert bike_session["target_duration_s"] > run_session["target_duration_s"]
    for s in (bike_session, run_session):
        expected = round(
            s["target_duration_s"] / 3600 * _tss_per_hour(s["sport"], s["session_type"]), 2
        )
        assert s["target_tss"] == expected


def test_training_day_session_pma_uses_dedicated_tss_per_hour() -> None:
    from garmin_sync.coach.planner import _training_day_session, _tss_per_hour

    session = _training_day_session(
        day=date.today(),
        phase="peak",
        week_offset=0,
        stype="pma",
        sport="bike",
        tss_by_sport={"bike": 60.0},
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={},
        sport_elevation_weight_total={},
    )
    assert session["session_type"] == "pma"
    expected_tss = round(session["target_duration_s"] / 3600 * _tss_per_hour("bike", "pma"), 2)
    assert session["target_tss"] == expected_tss
    # pma bike peak bounds: 40-60min (Task 4)
    assert 40 * 60 <= session["target_duration_s"] <= 60 * 60


def test_training_day_session_sprint_gets_no_elevation_target() -> None:
    from garmin_sync.coach.planner import _training_day_session

    session = _training_day_session(
        day=date.today(),
        phase="peak",
        week_offset=0,
        stype="sprint",
        sport="bike",
        tss_by_sport={"bike": 60.0},
        sport_weight_total={"bike": 1.0},
        weekly_elevation_by_sport={"bike": 200},
        sport_elevation_weight_total={"bike": 1.0},
    )
    assert not session.get("target_elevation_gain_m")


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
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
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


def test_build_week_sessions_tss_consistent_with_clamped_duration() -> None:
    """After duration clamping, each session's target_tss is re-derived from its
    target_duration_s, so the two stay internally consistent. The weekly budget is
    intentionally no longer exactly conserved (realistic durations take precedence)."""
    from garmin_sync.coach.planner import _build_week_sessions, _tss_per_hour

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=week_start,
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
        is_last_week=False,
        race_date=today + timedelta(days=365),
        race_sport="run",
    )
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert training
    for s in training:
        expected = round(
            s["target_duration_s"] / 3600 * _tss_per_hour(s["sport"], s["session_type"]), 2
        )
        assert s["target_tss"] == expected


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
    assert "pma" not in types
    assert "endurance" in types


def test_level3_build_allows_threshold_not_intervals() -> None:
    types = pick_session_types_for_phase("build", max_level=3)
    assert "threshold" in types
    assert "intervals" not in types
    assert "pma" not in types


def test_advanced_peak_allows_pma_and_sprint() -> None:
    types = pick_session_types_for_phase("peak", max_level=5)
    assert "pma" in types
    assert "sprint" in types


def test_weekly_tss_floor_scales_with_hours() -> None:
    from garmin_sync.coach.planner import weekly_tss_floor_from_hours

    assert weekly_tss_floor_from_hours(8) == 360
    assert weekly_tss_floor_from_hours(None) == 0


def _count(sessions, stype):
    return sum(1 for s in sessions if s["session_type"] == stype)


def test_build_week_caps_training_days_when_all_available() -> None:
    from garmin_sync.coach.planner import _build_week_sessions

    # With equal strengths=3, each sport gets an equal share: round(400/3, 2) = 133.33
    sessions = _build_week_sessions(
        week_offset=0,
        phase="build",
        week_start=date(2026, 6, 22),  # Monday
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 133.33, "bike": 133.33, "run": 133.33},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        is_last_week=False,
        race_date=date(2026, 9, 1),
        race_sport="run",
    )
    assert len(sessions) == 7
    assert _count(sessions, "rest") >= 1
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert len(training) == 5


def test_build_week_clamps_bike_endurance_duration() -> None:
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        week_offset=0,
        phase="base",
        week_start=date(2026, 6, 22),
        sports_in_race=["bike"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"bike": 120.0},
        available_days=["mon", "wed", "fri"],
        hours_per_week=6,
        is_last_week=False,
        race_date=date(2026, 9, 1),
        race_sport="bike",
    )
    bike_end = [s for s in sessions if s["sport"] == "bike" and s["session_type"] == "endurance"]
    assert bike_end
    assert all(s["target_duration_s"] >= 90 * 60 for s in bike_end)


def test_generate_plan_uses_history_adjusted_discipline_level(monkeypatch) -> None:
    """generate_plan must pass effective (history-adjusted) strengths
    to _build_week_sessions, not the raw declared values."""
    from garmin_sync.coach import planner as p_mod
    from garmin_sync.coach.discipline_level import DisciplineLevel, DisciplineLevels

    profile = {
        "user_id": "u-eff",
        "hours_per_week": 6,
        "ftp_watts": 200,
        "fc_max_bpm": 180,
        "sports_strengths": {"swim": 3, "bike": 2, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    race = {
        "id": "rg-eff",
        "race_date": (date.today() + timedelta(weeks=8)).isoformat(),
        "discipline": "triathlon",
        "legs": [
            {
                "order": 1,
                "discipline": "swim",
                "distance_km": 1.4,
                "elevation_gain_m": 0,
            },
            {
                "order": 2,
                "discipline": "bike",
                "distance_km": 53,
                "elevation_gain_m": 2200,
            },
            {
                "order": 3,
                "discipline": "run",
                "distance_km": 8,
                "elevation_gain_m": 200,
            },
        ],
    }

    def _table_router(table_name: str):
        m = MagicMock()
        if table_name == "athlete_profiles":
            chain = m.select.return_value.eq.return_value.single.return_value.execute.return_value
            chain.data = profile
        elif table_name == "race_goals":
            eqq = m.select.return_value.eq.return_value.eq.return_value
            chain = eqq.maybe_single.return_value.execute.return_value
            chain.data = race
        elif table_name == "activities":
            sel = m.select.return_value.eq.return_value.gte.return_value.execute.return_value
            sel.data = []
        elif table_name == "training_plans":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            m.insert.return_value.execute.return_value.data = [{"id": "plan-eff"}]
        elif table_name == "planned_sessions":
            m.insert.return_value.execute.return_value.data = []
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    # Fake effective strengths: bike bumped 2 -> 3
    fake_levels = DisciplineLevels(
        disciplines={
            "swim": DisciplineLevel(3, 3, 0, "high", "ok", {}),
            "bike": DisciplineLevel(2, 3, 1, "high", "bumped", {}),
            "run": DisciplineLevel(3, 3, 0, "high", "ok", {}),
        }
    )
    monkeypatch.setattr(
        p_mod,
        "load_effective_strengths",
        lambda *_a, **_kw: fake_levels.effective_strengths,
    )

    captured_kwargs: list[dict] = []
    original_build = p_mod._build_week_sessions

    def _capturing_build(**kwargs):
        captured_kwargs.append(kwargs)
        return original_build(**kwargs)

    monkeypatch.setattr(p_mod, "_build_week_sessions", _capturing_build)

    result = generate_plan("u-eff")
    assert result["status"] == "ok"
    assert captured_kwargs, "_build_week_sessions was never called"
    for kw in captured_kwargs:
        assert kw["sports_strengths"] == {"swim": 3, "bike": 3, "run": 3}, (
            f"Expected effective strengths, got {kw['sports_strengths']}"
        )


def test_cap_limits_run_increase_to_10pct() -> None:
    out = cap_weekly_ramp_by_sport({"run": 150.0}, {"run": 100.0})
    assert out["run"] == 110.0  # +10% max


def test_cap_does_not_limit_decreases() -> None:
    out = cap_weekly_ramp_by_sport({"run": 70.0}, {"run": 100.0})
    assert out["run"] == 70.0  # baisse (deload) non bridée


def test_cap_no_prev_is_passthrough() -> None:
    assert cap_weekly_ramp_by_sport({"run": 200.0}, None) == {"run": 200.0}


def test_cap_missing_sport_in_prev_not_capped() -> None:
    out = cap_weekly_ramp_by_sport({"swim": 80.0, "run": 150.0}, {"run": 100.0})
    assert out["swim"] == 80.0  # pas de précédent swim -> non bridé
    assert out["run"] == 110.0


def test_cap_bike_uses_its_own_cap() -> None:
    out = cap_weekly_ramp_by_sport({"bike": 200.0}, {"bike": 100.0})
    assert out["bike"] == 120.0  # vélo +20%


def test_post_deload_rebound_not_throttled() -> None:
    """Post-deload week must rebound to the pre-deload sustained level, not
    be throttled to deload_tss * 1.10.

    Simulates the conditional-prev threading for three consecutive weeks:
      offset=2 (normal, build)   → prev updated to sustained level
      offset=3 (deload, build)   → (offset+1)%4==0 → prev NOT updated
      offset=4 (normal, build)   → rebound allowed (prev still = week3 level)

    Without the fix, prev would be updated to the deload TSS and week5 run
    would be capped at deload*1.10 ≈ 0.77*S.  With the fix, prev stays at S
    and the rebound week is only capped at S*1.10, allowing full recovery.
    """
    sports = ["run"]
    strengths = {"run": 3}
    sustained_tss = 100.0
    deload_tss = 70.0  # ~0.7 * sustained (mirrors DELOAD_RAMP_RATE)

    prev: dict[str, float] | None = None
    deload_run = 0.0
    rebound_run = 0.0
    for offset, weekly_tss in [(2, sustained_tss), (3, deload_tss), (4, sustained_tss)]:
        phase: str = "build"
        tss_by_sport = distribute_weekly_tss_by_sport(
            weekly_tss=weekly_tss, sports_in_race=sports, sports_strengths=strengths
        )
        tss_by_sport = cap_weekly_ramp_by_sport(tss_by_sport, prev)
        is_reduction_week = phase == "taper" or (offset + 1) % 4 == 0
        if not is_reduction_week:
            prev = tss_by_sport
        if offset == 3:
            deload_run = tss_by_sport["run"]
        if offset == 4:
            rebound_run = tss_by_sport["run"]

    # The rebound must NOT be capped at deload*1.10 (≈ 77)
    # because prev was preserved at the sustained level during the deload.
    assert rebound_run > deload_run * 1.10, (
        f"Post-deload rebound was throttled: rebound={rebound_run}, "
        f"deload={deload_run}, 10%-above-deload={deload_run * 1.10:.2f}"
    )
    # And the rebound must not wildly overshoot (capped at sustained*1.10)
    assert rebound_run <= sustained_tss * 1.10 + 0.01


def test_distribute_then_cap_run_never_exceeds_10pct_week_over_week() -> None:
    # simule 2 semaines consécutives : la 2e demande +50% sur run -> bridée à +10%.
    w1 = cap_weekly_ramp_by_sport(
        distribute_weekly_tss_by_sport(
            weekly_tss=200,
            sports_in_race=["run", "bike"],
            sports_strengths={"run": 1, "bike": 5},
            progress=0.5,
        ),
        None,
    )
    w2 = cap_weekly_ramp_by_sport(
        distribute_weekly_tss_by_sport(
            weekly_tss=320,
            sports_in_race=["run", "bike"],
            sports_strengths={"run": 1, "bike": 5},
            progress=1.0,
        ),
        w1,
    )
    assert w2["run"] <= round(w1["run"] * 1.10, 2) + 0.01
