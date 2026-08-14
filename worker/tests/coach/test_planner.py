"""Tests for the plan orchestrator (generate_plan)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from garmin_sync.coach.activity_review import build_activity_review
from garmin_sync.coach.planner import (
    DELOAD_RAMP_RATE,
    NORMAL_RAMP_RATE,
    TAPER_RAMP_RATE,
    ObservedHabits,
    TrainingTarget,
    WeekSlot,
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
    # day_idx=1 (mardi) n'est pas un slot réservé (long=dernier jour d'entraînement,
    # recovery=lundi/jeudi), donc _pick_session_type applique l'anti back-to-back hard.
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
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=week_start,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=today + timedelta(days=365), sport="run"),
    )

    # Le dernier jour d'entraînement porte la séance 'long' (cf. long_session_day)
    long_sessions = [s for s in sessions if s["session_type"] == "long"]
    endurance_sessions = [s for s in sessions if s["session_type"] == "endurance"]
    assert len(long_sessions) >= 1
    assert len(endurance_sessions) >= 1

    # Long must be heavier than endurance in TSS (within same sport)
    long_sport = long_sessions[0]["sport"]
    same_sport_endurance = [s for s in endurance_sessions if s["sport"] == long_sport]
    max_long_tss = max(s["target_tss"] for s in long_sessions)
    if same_sport_endurance:
        assert max_long_tss > max(s["target_tss"] for s in same_sport_endurance)
    # Et plus longue que toute endurance du même sport en durée.
    max_long_duration = max(s["target_duration_s"] for s in long_sessions)
    for s in same_sport_endurance:
        assert max_long_duration > s["target_duration_s"]


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


_PHASES_12W = [
    (0, "base"),
    (1, "base"),
    (2, "base"),
    (3, "base"),
    (4, "base"),
    (5, "base"),
    (6, "base"),
    (7, "build"),
    (8, "build"),
    (9, "build"),
    (10, "peak"),
    (11, "taper"),
]


def test_compute_weekly_elevation_targets_respects_thresholds() -> None:
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    # Hilly tri: bike 2200, run 200 -> both above threshold (>=300 / >=100)
    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"swim": 0, "bike": 2200, "run": 200},
        week_offset=5,
        phases=_PHASES_12W,
    )
    assert out["bike"] > 0
    assert out["run"] > 0
    assert out["swim"] == 0


def test_compute_weekly_elevation_targets_zero_on_flat_race() -> None:
    """A flat 10K route race -> all sports below threshold -> no hill training."""
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"run": 50}, week_offset=3, phases=_PHASES_12W
    )
    assert out == {"run": 0}


def test_elevation_progression_reaches_race_dplus_at_peak() -> None:
    """Régression #131 : la cible hebdo doit ATTEINDRE le D+ de course en fin de
    build/peak (prod : jamais plus de 500 m/sem pour une course à 2000 m)."""
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=10,  # semaine peak
        phases=_PHASES_12W,
        observed_weekly_dplus={"bike": 500},
    )
    assert out["bike"] >= 2000, f"le pic doit couvrir le D+ de course, obtenu {out['bike']}"


def test_elevation_progression_starts_from_observed_load() -> None:
    """Le point de départ est le D+ réellement encaissé, pas zéro ni un étalement."""
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=0,
        phases=_PHASES_12W,
        observed_weekly_dplus={"bike": 500},
    )
    assert out["bike"] == 500


def test_elevation_progression_bounded_by_weekly_ramp_cap() -> None:
    from garmin_sync.coach.planner import WEEKLY_RAMP_CAP, compute_weekly_elevation_targets

    prev = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=3,
        phases=_PHASES_12W,
        observed_weekly_dplus={"bike": 400},
    )
    cur = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=4,
        phases=_PHASES_12W,
        observed_weekly_dplus={"bike": 400},
    )
    assert cur["bike"] <= prev["bike"] * WEEKLY_RAMP_CAP["bike"] + 1  # +1 = arrondi


def test_elevation_athlete_already_at_race_level_is_maintained() -> None:
    """Athlète A : 2058 m/sem encaissés pour 2000 m de course. Le coach ne doit
    pas retomber à 500 m/sem (et déclencher elevation_spike dans le même écran)."""
    from garmin_sync.coach.planner import compute_weekly_elevation_targets

    out = compute_weekly_elevation_targets(
        race_dplus_by_sport={"bike": 2000},
        week_offset=2,
        phases=_PHASES_12W,
        observed_weekly_dplus={"bike": 2058},
    )
    assert out["bike"] >= 1800, f"la charge D+ déjà encaissée doit être maintenue : {out}"


def test_observed_weekly_elevation_by_sport_averages_28_days() -> None:
    from garmin_sync.coach.planner import observed_weekly_elevation_by_sport

    today = date(2026, 8, 2)
    activities = [
        {"start_time": "2026-07-28T08:00:00Z", "sport": "cycling", "elevation_gain_m": 1000},
        {"start_time": "2026-07-20T08:00:00Z", "sport": "cycling", "elevation_gain_m": 1000},
        {"start_time": "2026-07-12T08:00:00Z", "sport": "running", "elevation_gain_m": 200},
        # Hors fenêtre : ignorée
        {"start_time": "2026-05-01T08:00:00Z", "sport": "cycling", "elevation_gain_m": 5000},
    ]
    out = observed_weekly_elevation_by_sport(activities, today=today)
    assert out["bike"] == 500  # 2000 m sur 4 semaines
    assert out["run"] == 50


def test_build_week_sessions_long_session_gets_more_elevation() -> None:
    """Hilly race: long bike must receive > endurance bike D+ target."""
    from garmin_sync.coach.planner import _build_week_sessions

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=week_start,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=today + timedelta(days=365), sport="run"),
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
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=week_start,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 140.0, "bike": 140.0, "run": 140.0},
        available_days=["tue", "wed", "thu", "sat", "fri", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=today + timedelta(days=365), sport="run"),
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
    # Archivage scopé à l'utilisateur (un seul .eq) et non plus à la course.
    tp_mock.select.return_value.eq.return_value.execute.return_value.data = [{"id": "old-plan-1"}]
    tp_mock.update.return_value.in_.return_value.execute.return_value = MagicMock()
    tp_mock.insert.return_value.execute.return_value.data = [{"id": "plan-2"}]

    ps_mock = MagicMock()
    # Requête de report des workouts déjà générés : aucune séance existante ici.
    ps_mock.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
    ps_mock.delete.return_value.in_.return_value.gte.return_value.execute.return_value = MagicMock()

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

    # 1. Seules les séances FUTURES des plans précédents sont supprimées.
    ps_mock.delete.assert_called_once()
    delete_in_args, _ = ps_mock.delete.return_value.in_.call_args
    assert delete_in_args[0] == "plan_id"
    assert delete_in_args[1] == ["old-plan-1"]
    delete_gte_args, _ = ps_mock.delete.return_value.in_.return_value.gte.call_args
    assert delete_gte_args == ("date", date.today().isoformat()), (
        "le DELETE doit être borné aux séances futures (l'historique passé est conservé)"
    )

    # 2. previous training_plans archived
    tp_mock.update.assert_called_once()
    update_args, _ = tp_mock.update.call_args
    assert update_args[0]["status"] == "archived"
    update_in_args, _ = tp_mock.update.return_value.in_.call_args
    assert update_in_args[0] == "id"
    assert update_in_args[1] == ["old-plan-1"]

    # 3. Les séances passées sont rattachées au nouveau plan (sinon l'historique
    #    disparaît : les pages lisent via jointure sur le plan ACTIF).
    reparent_args, _ = ps_mock.update.call_args
    assert reparent_args[0] == {"plan_id": "plan-2"}
    reparent_lt_args, _ = ps_mock.update.return_value.in_.return_value.lt.call_args
    assert reparent_lt_args == ("date", date.today().isoformat())


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


def test_weekly_tss_cap_scales_with_hours() -> None:
    from garmin_sync.coach.planner import weekly_tss_cap_from_hours

    assert weekly_tss_cap_from_hours(8) == 360
    assert weekly_tss_cap_from_hours(None) == 0


def test_base_weekly_tss_measured_ctl_is_primary() -> None:
    """Régression #128 : athlète A (ctl 21, 8 h déclarées) doit partir de sa
    charge MESURÉE (147 TSS), pas du plancher déclaré (360 = 2,3x le réel)."""
    from garmin_sync.coach.planner import compute_base_weekly_tss

    assert compute_base_weekly_tss(ctl=21, hours_per_week=8) == 147.0


def test_base_weekly_tss_declared_hours_are_a_feasibility_cap() -> None:
    """Les heures déclarées bornent le volume (on ne planifie pas plus que le
    budget temps), elles ne le gonflent jamais."""
    from garmin_sync.coach.planner import compute_base_weekly_tss

    assert compute_base_weekly_tss(ctl=80, hours_per_week=6) == 270.0


def test_base_weekly_tss_cold_start_falls_back_to_declared_cap() -> None:
    from garmin_sync.coach.planner import compute_base_weekly_tss

    assert compute_base_weekly_tss(ctl=0, hours_per_week=8) == 360.0


def test_base_weekly_tss_without_hours_uses_measured() -> None:
    from garmin_sync.coach.planner import compute_base_weekly_tss

    assert compute_base_weekly_tss(ctl=30, hours_per_week=None) == 210.0


def _count(sessions, stype):
    return sum(1 for s in sessions if s["session_type"] == stype)


def test_build_week_caps_training_days_when_all_available() -> None:
    from garmin_sync.coach.planner import _build_week_sessions

    # With equal strengths=3, each sport gets an equal share: round(400/3, 2) = 133.33
    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="build",
            start=date(2026, 6, 22),  # Monday,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"swim": 133.33, "bike": 133.33, "run": 133.33},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="run"),
    )
    assert len(sessions) == 7
    assert _count(sessions, "rest") >= 1
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert len(training) == 5


def test_build_week_clamps_bike_endurance_duration() -> None:
    """Budget aligné sur les 6 h déclarées depuis #164 (6 x 45 = 270 TSS) : à 120,
    une semaine de trois sorties vélo ne payait plus d'endurance à côté de sa
    longue, et la séance était rétrogradée en récup."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["bike"],
        sports_strengths={"swim": 3, "bike": 3, "run": 3},
        tss_by_sport={"bike": 250.0},
        available_days=["mon", "wed", "fri"],
        hours_per_week=6,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="bike"),
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


def test_build_week_strong_bike_gets_threshold_despite_weak_run() -> None:
    """Régression #121 : le niveau 1 en course ne doit pas interdire le seuil en
    vélo (niveau 4). Le plafond d'intensité est PAR discipline, pas le min global."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="build",
            start=date(2026, 6, 22),  # Monday,
            is_last=False,
            progress=1.0,
        ),
        sports_in_race=["bike", "run"],
        sports_strengths={"swim": 2, "bike": 4, "run": 1},
        tss_by_sport={"bike": 200.0, "run": 80.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="bike"),
    )
    bike_types = {s["session_type"] for s in sessions if s["sport"] == "bike"}
    run_types = {s["session_type"] for s in sessions if s["sport"] == "run"}
    assert bike_types & {"threshold", "pma"}, (
        f"le vélo (niveau 4) doit avoir de l'intensité en build, obtenu : {bike_types}"
    )
    assert not (run_types & {"threshold", "pma", "sprint"}), (
        f"la course (niveau 1) doit rester protégée, obtenu : {run_types}"
    )


def test_build_week_four_days_without_sunday_still_has_long() -> None:
    """Régression #122 : la séance longue n'était attribuable que le dimanche,
    or le sélecteur retenait lun/mer/ven/sam -> 0 séance longue depuis mai.
    La longue doit suivre le dernier jour d'entraînement de la semaine."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=date(2026, 6, 22),  # Monday,
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 1, "bike": 1, "run": 1},  # beginner -> 4 jours
        tss_by_sport={"swim": 50.0, "bike": 50.0, "run": 50.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="run"),
    )
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    trained_days = {date.fromisoformat(s["date"]).weekday() for s in training}
    long_sessions = [s for s in training if s["session_type"] == "long"]
    assert len(long_sessions) >= 1, f"aucune séance longue (jours : {sorted(trained_days)})"
    # La longue tombe le dernier jour d'entraînement, dimanche sélectionné ou pas.
    assert date.fromisoformat(long_sessions[0]["date"]).weekday() == max(trained_days)


def test_estimate_race_time_shares_bike_dominant_on_hilly_tri() -> None:
    """Course de l'athlète A : vélo 47 km / 2000 m D+ ~ 60 % du temps estimé."""
    from garmin_sync.coach.planner import estimate_race_time_shares

    legs = [
        {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
        {"order": 2, "discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000},
        {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
    ]
    shares = estimate_race_time_shares(legs)
    assert abs(sum(shares.values()) - 1.0) < 1e-6
    assert shares["bike"] > 0.5, f"le vélo doit dominer : {shares}"
    assert shares["bike"] > shares["run"] > shares["swim"]


def test_estimate_race_time_shares_sums_duplicate_legs() -> None:
    """Duathlon run-bike-run : les deux segments course s'additionnent."""
    from garmin_sync.coach.planner import estimate_race_time_shares

    legs = [
        {"order": 1, "discipline": "run", "distance_km": 5, "elevation_gain_m": 0},
        {"order": 2, "discipline": "bike", "distance_km": 20, "elevation_gain_m": 0},
        {"order": 3, "discipline": "run", "distance_km": 5, "elevation_gain_m": 0},
    ]
    shares = estimate_race_time_shares(legs)
    assert set(shares) == {"run", "bike"}
    assert shares["run"] > shares["bike"]


def test_build_week_bike_heavy_race_gets_at_least_as_many_bike_as_swim() -> None:
    """Régression #130 : la répartition suit l'enjeu de course (temps estimé),
    plus l'ordre chronologique des legs (swim, bike, run, swim en prod).

    Budget vélo revu à la hausse depuis #164 : une sortie longue de 2 h 30 coûte
    112,5 TSS et une séance au seuil 90 — la semaine doit pouvoir les payer, sinon
    la longue est rétrogradée au lieu de faire déborder le budget."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="build",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 2, "bike": 4, "run": 1},
        tss_by_sport={"swim": 60.0, "bike": 240.0, "run": 90.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(
            race_day=date(2026, 9, 1),
            sport="bike",
            time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        ),
    )
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    n_bike = sum(1 for s in training if s["sport"] == "bike")
    n_swim = sum(1 for s in training if s["sport"] == "swim")
    assert n_bike >= n_swim, f"bike={n_bike} < swim={n_swim}"
    assert n_bike >= 2
    # La séance longue porte sur la discipline dominante de l'épreuve.
    long_sessions = [s for s in training if s["session_type"] == "long"]
    assert long_sessions
    assert long_sessions[0]["sport"] == "bike"


def test_build_week_uses_declared_budget_with_five_days() -> None:
    """Régression #129 : 8 h déclarées / 7 jours dispo ne doivent plus être
    plafonnés à 4 jours par un classement « beginner » dû au point faible run.
    Le run reste protégé par son cap PAR discipline (niveau run 1 -> 2 j max).

    Budget aligné sur les 8 h déclarées depuis #164 (8 x 45 = 360 TSS) : à 180, la
    semaine ne payait pas ses cinq séances et l'une d'elles était retirée."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 2, "bike": 4, "run": 1},
        tss_by_sport={"swim": 90.0, "bike": 180.0, "run": 90.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(race_day=date(2026, 9, 1), sport="bike"),
    )
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    assert len(training) == 5, f"attendu 5 jours (intermediate), obtenu {len(training)}"
    n_run = sum(1 for s in training if s["sport"] == "run")
    assert n_run <= 2, f"le run niveau 1 doit rester cappé à 2 j/sem : {n_run}"


def test_observed_weekday_usage_counts_and_durations() -> None:
    from garmin_sync.coach.planner import observed_weekday_usage

    today = date(2026, 8, 2)  # dimanche
    activities = [
        # Deux gros vélos le samedi (weekday 5)
        {"start_time": "2026-07-25T09:00:00Z", "sport": "cycling", "duration_s": 9000},
        {"start_time": "2026-07-18T09:00:00Z", "sport": "cycling", "duration_s": 8000},
        # Un run le mardi (weekday 1)
        {"start_time": "2026-07-28T07:00:00Z", "sport": "running", "duration_s": 2400},
        # Hors fenêtre : ignoré
        {"start_time": "2026-05-01T09:00:00Z", "sport": "cycling", "duration_s": 9000},
    ]
    counts, durations = observed_weekday_usage(activities, today=today)
    assert counts == {5: 2, 1: 1}
    assert durations[5] == 17000.0
    assert durations[1] == 2400.0


def test_build_week_places_sessions_on_athlete_observed_days() -> None:
    """Régression #127 : 0 correspondance prévu/réalisé sur 20 jours parce que
    la grille mécanique ignorait les jours réellement utilisés. Les jours et la
    séance longue doivent suivre le comportement observé."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="base",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 1, "bike": 1, "run": 1},  # beginner -> 4 jours
        tss_by_sport={"swim": 50.0, "bike": 120.0, "run": 50.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(
            race_day=date(2026, 9, 1),
            sport="bike",
            time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        ),
        observed=ObservedHabits(
            weekday_counts={1: 3, 3: 2, 5: 4, 6: 3},
            weekday_durations={1: 3600.0, 3: 4000.0, 5: 16000.0, 6: 7000.0},
        ),
    )
    training = [s for s in sessions if s["session_type"] not in ("rest", "race")]
    trained_days = {date.fromisoformat(s["date"]).weekday() for s in training}
    assert trained_days == {1, 3, 5, 6}, f"jours {sorted(trained_days)} != habitudes athlète"
    long_sessions = [s for s in training if s["session_type"] == "long"]
    assert long_sessions, "il faut une séance longue"
    # La longue tombe le samedi, jour des grosses sorties observées.
    assert date.fromisoformat(long_sessions[0]["date"]).weekday() == 5


def test_compute_tss_by_date_resolves_fc_max_from_observed_hr() -> None:
    """Raccord lot A (#120/#134) : fc_max_bpm NULL en prod ne doit plus faire
    retomber le TSS du planner sur le tier plat durée x 50 quand des hr_max
    observés permettent de résoudre une FCmax."""
    from garmin_sync.coach.planner import _compute_tss_by_date

    today = date(2026, 8, 2)
    activities = [
        {
            "start_time": "2026-07-30T08:00:00Z",
            "sport": "running",
            "duration_s": 3600,
            "power_avg": None,
            "hr_avg": 140,
            "hr_max": 185,
            "tss": None,
        }
    ]
    profile = {"ftp_watts": None, "fc_max_bpm": None}
    out = _compute_tss_by_date(activities, profile, today=today)
    assert out[date(2026, 7, 30)] != 50.0, "tier plat durée x 50 encore actif"


def test_build_week_peak_phase_has_quality_session_for_strong_sport() -> None:
    """Le premier créneau éligible d'un sport prend une séance de qualité : une
    semaine peak d'un vélo niveau 4 doit contenir pma ou sprint, même quand la
    rotation ne laisse qu'un ou deux créneaux au sport."""
    from garmin_sync.coach.planner import _build_week_sessions

    sessions = _build_week_sessions(
        slot=WeekSlot(
            offset=0,
            phase="peak",
            start=date(2026, 6, 22),
            is_last=False,
        ),
        sports_in_race=["swim", "bike", "run"],
        sports_strengths={"swim": 2, "bike": 4, "run": 1},
        tss_by_sport={"swim": 40.0, "bike": 150.0, "run": 60.0},
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        hours_per_week=8,
        target=TrainingTarget(
            race_day=date(2026, 9, 1),
            sport="bike",
            time_shares={"swim": 0.11, "bike": 0.66, "run": 0.23},
        ),
    )
    bike_types = {s["session_type"] for s in sessions if s["sport"] == "bike"}
    assert bike_types & {"pma", "sprint"}, f"semaine peak sans intensité vélo : {bike_types}"


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


def test_observed_weekly_elevation_credits_brick_dplus_to_the_bike() -> None:
    """#169: a multi_sport was dropped from the observed D+ entirely, so the
    ramp restarted from a fraction of the race D+ despite real climbing done.

    Its D+ is earned on the bike leg — crediting it to run too would double-count
    it and inflate the run ramp toward injury.
    """
    from garmin_sync.coach.planner import observed_weekly_elevation_by_sport

    today = date(2026, 8, 14)
    activities = [
        {"start_time": "2026-08-08T08:00:00Z", "sport": "multi_sport", "elevation_gain_m": 952},
        {"start_time": "2026-08-01T08:00:00Z", "sport": "cycling", "elevation_gain_m": 1048},
    ]
    out = observed_weekly_elevation_by_sport(activities, today=today)
    assert out["bike"] == 500  # (952 + 1048) / 4 semaines
    assert "run" not in out
    assert "brick" not in out
