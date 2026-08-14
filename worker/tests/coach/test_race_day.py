"""Tests du contenu déterministe du jour de course (issue #157)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_sync.coach.planner import carry_over_workouts, generate_plan
from garmin_sync.coach.race_day import (
    RACE_SPEED_KMH,
    build_race_day_session,
    estimate_race_segments,
)
from garmin_sync.coach.sessions import _should_skip_workout_generation
from garmin_sync.coach.workout_schema import Workout

# Triathlon de la Madelaine 2026 — le cas réel à faire fonctionner.
MADELAINE_LEGS: list[dict[str, Any]] = [
    {"order": 1, "discipline": "swim", "distance_km": 1.4, "elevation_gain_m": 0},
    {"order": 2, "discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000},
    {"order": 3, "discipline": "run", "distance_km": 8, "elevation_gain_m": 200},
]
RACE_DAY = date(2026, 8, 22)

ATHLETE_FULL: dict[str, Any] = {
    "fc_max_bpm": 190,
    "ftp_watts": 220,
    "vma_kmh": 16.0,
    "css_per_100m_s": 110,
    "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
}
ATHLETE_BARE: dict[str, Any] = {}


def _session(
    legs: list[dict[str, Any]] | None = None,
    *,
    athlete: dict[str, Any] | None = None,
    race_sport: str = "triathlon",
) -> dict[str, Any]:
    return build_race_day_session(
        day=RACE_DAY,
        race_sport=race_sport,
        week_offset=7,
        legs=MADELAINE_LEGS if legs is None else legs,
        athlete=ATHLETE_FULL if athlete is None else athlete,
    )


def _workout(session: dict[str, Any]) -> Workout:
    """Le workout persisté doit toujours revalider contre le schéma Pydantic."""
    return Workout.model_validate(session["workout"])


# --- Segments ---------------------------------------------------------------


def test_segments_follow_leg_order_with_durations() -> None:
    segments = estimate_race_segments(MADELAINE_LEGS, athlete=ATHLETE_FULL)
    assert [s.discipline for s in segments] == ["swim", "bike", "run"]
    assert all(s.duration_s > 0 for s in segments)


def test_climbing_slows_a_segment_down() -> None:
    flat = estimate_race_segments(
        [{"discipline": "bike", "distance_km": 47, "elevation_gain_m": 0}], athlete=ATHLETE_BARE
    )
    hilly = estimate_race_segments(
        [{"discipline": "bike", "distance_km": 47, "elevation_gain_m": 2000}], athlete=ATHLETE_BARE
    )
    assert hilly[0].duration_s > flat[0].duration_s


def test_missing_elevation_is_treated_as_flat() -> None:
    without = estimate_race_segments(
        [{"discipline": "run", "distance_km": 10}], athlete=ATHLETE_BARE
    )
    zeroed = estimate_race_segments(
        [{"discipline": "run", "distance_km": 10, "elevation_gain_m": 0}], athlete=ATHLETE_BARE
    )
    assert without[0].duration_s == zeroed[0].duration_s


def test_leg_without_usable_distance_is_dropped() -> None:
    segments = estimate_race_segments(
        [
            {"discipline": "swim"},
            {"discipline": "bike", "distance_km": 0, "elevation_gain_m": 500},
            {"discipline": "run", "distance_km": 10},
        ],
        athlete=ATHLETE_BARE,
    )
    assert [s.discipline for s in segments] == ["run"]


def test_unknown_discipline_falls_back_on_a_default_speed() -> None:
    segments = estimate_race_segments(
        [{"discipline": "kayak", "distance_km": 12}], athlete=ATHLETE_BARE
    )
    assert segments[0].duration_s > 0


def test_reference_speeds_apply_without_any_performance_data() -> None:
    segments = estimate_race_segments(
        [{"discipline": "run", "distance_km": 10}], athlete=ATHLETE_BARE
    )
    assert segments[0].duration_s == pytest.approx(3600 * 10 / RACE_SPEED_KMH["run"], rel=0.01)


def test_a_stronger_athlete_is_given_a_faster_estimate() -> None:
    weak = estimate_race_segments(
        [{"discipline": "bike", "distance_km": 47}],
        athlete={"sports_strengths": {"bike": 1}},
    )
    strong = estimate_race_segments(
        [{"discipline": "bike", "distance_km": 47}],
        athlete={"sports_strengths": {"bike": 5}},
    )
    assert strong[0].duration_s < weak[0].duration_s


def test_run_pace_derives_from_vma_when_known() -> None:
    generic = estimate_race_segments(
        [{"discipline": "run", "distance_km": 10}], athlete=ATHLETE_BARE
    )
    fast = estimate_race_segments(
        [{"discipline": "run", "distance_km": 10}], athlete={"vma_kmh": 20.0}
    )
    assert fast[0].duration_s < generic[0].duration_s


def test_swim_pace_derives_from_css_when_known() -> None:
    slow = estimate_race_segments(
        [{"discipline": "swim", "distance_km": 1.4}], athlete={"css_per_100m_s": 140}
    )
    fast = estimate_race_segments(
        [{"discipline": "swim", "distance_km": 1.4}], athlete={"css_per_100m_s": 90}
    )
    assert fast[0].duration_s < slow[0].duration_s


# --- Séance du jour J -------------------------------------------------------


def test_madelaine_race_day_is_not_an_empty_slot() -> None:
    session = _session()
    assert session["date"] == "2026-08-22"
    assert session["sport"] == "triathlon"
    assert session["session_type"] == "race"
    assert session["phase"] == "race"
    assert session["week_offset"] == 7
    assert session["target_duration_s"] > 0
    assert session["target_tss"] > 0
    assert session["target_elevation_gain_m"] == 2200
    assert session["workout"] is not None


def test_madelaine_estimate_stays_in_a_plausible_range() -> None:
    session = _session()
    hours = session["target_duration_s"] / 3600
    assert 3 < hours < 6


def test_target_duration_matches_the_workout_total() -> None:
    session = _session()
    assert _workout(session).total_duration_s() == session["target_duration_s"]


def test_workout_lists_every_segment_and_both_transitions() -> None:
    workout = _workout(_session())
    notes = [block.notes or "" for block in workout.main]
    assert len(notes) == 5  # 3 segments + T1 + T2
    assert "natation" in notes[0].lower()
    assert "T1" in notes[1]
    assert "vélo" in notes[2].lower()
    assert "T2" in notes[3]
    assert "course" in notes[4].lower()


def test_bike_segment_carries_its_distance_and_elevation() -> None:
    workout = _workout(_session())
    bike = workout.main[2]
    assert bike.distance_m == 47000
    assert "2000 m D+" in (bike.notes or "")


def test_transitions_carry_no_pace_or_power_target() -> None:
    """Pieds nus dans l'aire de transition : une allure ou des watts n'ont aucun sens."""
    workout = _workout(_session())
    for transition in (workout.main[1], workout.main[3]):
        assert transition.target.watts_low is None
        assert transition.target.pace_low_kmh is None
        assert transition.target.pace_per_100m_low_s is None


def test_workout_has_a_warmup_and_a_cooldown() -> None:
    workout = _workout(_session())
    assert workout.warmup.duration_s > 0
    assert workout.cooldown.duration_s > 0
    assert workout.technical_focus


def test_summary_covers_pacing_nutrition_and_transitions() -> None:
    summary = _workout(_session()).summary_md.lower()
    assert "allure" in summary
    assert "hydratation" in summary or "boire" in summary
    assert "glucides" in summary
    assert "transition" in summary


def test_fueling_advice_scales_with_race_duration() -> None:
    short = _workout(
        _session([{"discipline": "run", "distance_km": 5}], race_sport="run")
    ).summary_md
    long = _workout(_session()).summary_md
    assert short != long
    assert "sodium" in long.lower()
    assert "sodium" not in short.lower()


def test_a_very_long_race_drops_to_the_lowest_sustainable_intensity() -> None:
    """Format Ironman : au-delà de 6 h, l'intensité tenable retombe en Z2."""
    session = _session(
        [
            {"discipline": "swim", "distance_km": 3.8},
            {"discipline": "bike", "distance_km": 180, "elevation_gain_m": 1500},
            {"discipline": "run", "distance_km": 42.2, "elevation_gain_m": 200},
        ]
    )
    workout = _workout(session)
    assert session["target_duration_s"] > 6 * 3600
    assert workout.main[0].target.label == "Z2"
    assert "500-700 mg de sodium" in workout.summary_md


# --- Cibles chiffrées -------------------------------------------------------


def test_numeric_targets_are_filled_from_the_performance_profile() -> None:
    workout = _workout(_session())
    swim, bike, run = workout.main[0], workout.main[2], workout.main[4]
    assert swim.target.pace_per_100m_low_s
    assert swim.target.pace_per_100m_high_s
    assert bike.target.watts_low
    assert bike.target.watts_high
    assert run.target.pace_low_kmh
    assert run.target.pace_high_kmh
    assert all(b.target.bpm_low for b in (swim, bike, run))
    assert all(b.target.bpm_high for b in (swim, bike, run))


def test_race_day_content_survives_a_bare_profile() -> None:
    session = _session(athlete=ATHLETE_BARE)
    workout = _workout(session)
    assert session["target_duration_s"] > 0
    assert session["target_tss"] > 0
    assert workout.main[0].target.bpm_low is None
    assert workout.main[2].target.watts_low is None


# --- Course mono-discipline -------------------------------------------------


def test_single_discipline_race_has_no_transition_block() -> None:
    session = _session(
        [{"discipline": "run", "distance_km": 21.1, "elevation_gain_m": 300}], race_sport="run"
    )
    workout = _workout(session)
    assert len(workout.main) == 1
    assert session["target_elevation_gain_m"] == 300


def test_consecutive_legs_of_the_same_discipline_are_not_separated() -> None:
    """Duathlon run-bike-run : deux transitions, pas trois."""
    session = _session(
        [
            {"discipline": "run", "distance_km": 5},
            {"discipline": "bike", "distance_km": 20},
            {"discipline": "run", "distance_km": 2.5},
        ],
        race_sport="duathlon",
    )
    workout = _workout(session)
    assert len(workout.main) == 5


# --- Dégradations propres ---------------------------------------------------


@pytest.mark.parametrize("legs", [[], None, [{"discipline": "bike", "distance_km": 0}]])
def test_unusable_legs_degrade_to_an_empty_but_valid_session(legs: Any) -> None:
    session = build_race_day_session(
        day=RACE_DAY, race_sport="triathlon", week_offset=3, legs=legs, athlete=ATHLETE_FULL
    )
    assert session["target_duration_s"] is None
    assert session["target_tss"] is None
    assert session.get("workout") is None
    assert session["session_type"] == "race"
    assert session["week_offset"] == 3


def test_a_missing_athlete_profile_is_not_fatal() -> None:
    session = build_race_day_session(
        day=RACE_DAY, race_sport="triathlon", week_offset=0, legs=MADELAINE_LEGS, athlete=None
    )
    assert session["target_duration_s"] > 0
    assert _workout(session).total_duration_s() == session["target_duration_s"]


# --- Intégration : le plan généré, la reprise de workouts, le LLM -----------


def _generated_race_day(monkeypatch: Any) -> dict[str, Any]:
    """Lance generate_plan sur la Madelaine et retourne la séance du jour J."""
    from garmin_sync.coach import planner as p_mod

    race_date = date.today() + timedelta(weeks=8)
    profile = {
        "user_id": "u-race",
        "hours_per_week": 8,
        "ftp_watts": 220,
        "fc_max_bpm": 190,
        "vma_kmh": 16.0,
        "css_per_100m_s": 110,
        "sports_strengths": {"swim": 3, "bike": 3, "run": 3},
        "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    race = {
        "id": "rg-madelaine",
        "race_date": race_date.isoformat(),
        "discipline": "triathlon",
        "legs": MADELAINE_LEGS,
    }
    inserted: list[dict[str, Any]] = []

    def _table_router(table_name: str) -> MagicMock:
        m = MagicMock()
        if table_name == "athlete_profiles":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = (
                profile
            )
        elif table_name == "race_goals":
            chain = m.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value  # noqa: E501
            chain.data = race
        elif table_name == "activities":
            m.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []
        elif table_name == "training_plans":
            m.insert.return_value.execute.return_value.data = [{"id": "plan-race"}]
        elif table_name == "planned_sessions":
            m.insert.side_effect = lambda rows: MagicMock(
                execute=lambda: MagicMock(data=inserted.extend(rows))
            )
        return m

    fake_db = MagicMock()
    fake_db.table.side_effect = _table_router
    monkeypatch.setattr(p_mod, "get_admin_client", lambda: fake_db)

    assert generate_plan("u-race")["status"] == "ok"
    race_days = [s for s in inserted if s["date"] == race_date.isoformat()]
    assert len(race_days) == 1
    return race_days[0]


def test_generated_plan_ships_a_filled_race_day(monkeypatch: Any) -> None:
    session = _generated_race_day(monkeypatch)
    assert session["session_type"] == "race"
    assert session["sport"] == "triathlon"
    assert session["target_duration_s"] > 0
    assert session["target_tss"] > 0
    assert session["target_elevation_gain_m"] == 2200
    assert Workout.model_validate(session["workout"]).main


def test_carry_over_never_overwrites_a_freshly_built_race_day() -> None:
    fresh = _session()
    stale = {
        "date": fresh["date"],
        "sport": fresh["sport"],
        "session_type": fresh["session_type"],
        "target_duration_s": fresh["target_duration_s"],
        "workout": {"summary_md": "contenu périmé"},
        "workout_generated_at": "2026-01-01T00:00:00+00:00",
    }
    reused = carry_over_workouts([fresh], [stale])
    assert reused == 0
    assert fresh["workout"]["summary_md"] != "contenu périmé"


def test_race_day_is_never_sent_to_the_llm() -> None:
    assert _should_skip_workout_generation(
        {"sport": "triathlon", "session_type": "race", "target_duration_s": 15000}
    )
