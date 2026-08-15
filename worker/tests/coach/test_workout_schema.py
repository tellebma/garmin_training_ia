import re

import pytest
from pydantic import ValidationError

from garmin_sync.coach.workout_schema import (
    IntervalBlock,
    IntervalSet,
    IntervalTarget,
    Workout,
    describe_session_envelope,
    enrich_workout_targets,
    envelope_for_session,
    structure_caps_for_type,
    validate_workout_for_session,
)


def _plain_block(duration_s: int = 600, label: str = "Z2") -> IntervalBlock:
    return IntervalBlock(duration_s=duration_s, target=IntervalTarget(label=label, rpe=4))


def _plain_workout() -> Workout:
    return Workout(
        warmup=_plain_block(600, "Z1"),
        main=[_plain_block(2400, "Z2")],
        cooldown=_plain_block(600, "Z1"),
        summary_md="ok",
    )


@pytest.mark.parametrize("target_min", [167, 170, 174])
def test_long_ride_envelope_remains_satisfiable(target_min):
    """Cas d'échec observés en prod (issue #124) : longues sorties vélo 167-174 min.
    Un workout construit exactement sur les bornes de l'enveloppe doit passer la
    validation — sinon l'enveloppe est insatisfiable et le LLM ne peut que perdre."""
    session = {"session_type": "long", "sport": "bike", "target_duration_s": target_min * 60}
    env = envelope_for_session(session)
    main_s = env.target_s - env.warmup_max_s - env.cooldown_max_s
    workout = Workout(
        warmup=IntervalBlock(duration_s=env.warmup_max_s, target=IntervalTarget(label="Z1", rpe=2)),
        main=[IntervalBlock(duration_s=main_s, target=IntervalTarget(label="Z2", rpe=4))],
        cooldown=IntervalBlock(
            duration_s=env.cooldown_max_s, target=IntervalTarget(label="Z1", rpe=2)
        ),
        summary_md="ok",
    )
    assert validate_workout_for_session(workout, session) is workout


def test_block_accepts_optional_distance_m():
    b = IntervalBlock(duration_s=95, distance_m=100, target=IntervalTarget(label="Z4", rpe=8))
    assert b.distance_m == 100


def test_block_distance_m_defaults_to_none():
    assert _plain_block().distance_m is None


def test_block_rejects_non_positive_distance_m():
    target = IntervalTarget(label="Z4", rpe=8)
    with pytest.raises(ValidationError):
        IntervalBlock(duration_s=95, distance_m=0, target=target)


def test_target_accepts_swim_pace_per_100m_bounds():
    t = IntervalTarget(label="Z2", rpe=4, pace_per_100m_low_s=103, pace_per_100m_high_s=107)
    assert t.pace_per_100m_low_s == 103
    assert t.pace_per_100m_high_s == 107


def test_enrich_fills_bpm_bounds_from_fc_max():
    out = enrich_workout_targets(_plain_workout(), athlete={"fc_max_bpm": 195}, sport="run")
    z2 = out.main[0]
    assert isinstance(z2, IntervalBlock)
    assert z2.target.bpm_low == round(0.60 * 195)
    assert z2.target.bpm_high == round(0.70 * 195)
    assert out.warmup.target.bpm_low == round(0.50 * 195)  # Z1


def test_enrich_fills_watts_from_ftp_for_bike_only():
    athlete = {"fc_max_bpm": 195, "ftp_watts": 240}
    bike = enrich_workout_targets(_plain_workout(), athlete=athlete, sport="bike")
    run = enrich_workout_targets(_plain_workout(), athlete=athlete, sport="run")
    bike_main = bike.main[0]
    run_main = run.main[0]
    assert isinstance(bike_main, IntervalBlock)
    assert isinstance(run_main, IntervalBlock)
    assert bike_main.target.watts_low == round(0.56 * 240)
    assert bike_main.target.watts_high == round(0.75 * 240)
    assert run_main.target.watts_low is None


def test_enrich_fills_run_pace_from_vma():
    out = enrich_workout_targets(_plain_workout(), athlete={"vma_kmh": 17.0}, sport="run")
    main = out.main[0]
    assert isinstance(main, IntervalBlock)
    assert main.target.pace_low_kmh == pytest.approx(0.65 * 17.0, abs=0.1)
    assert main.target.pace_high_kmh == pytest.approx(0.75 * 17.0, abs=0.1)


def test_enrich_fills_swim_pace_per_100m_from_css():
    out = enrich_workout_targets(_plain_workout(), athlete={"css_per_100m_s": 95}, sport="swim")
    main = out.main[0]
    assert isinstance(main, IntervalBlock)
    # Z2 = CSS + 8..12 s/100m ; low = plus rapide (moins de secondes)
    assert main.target.pace_per_100m_low_s == 103
    assert main.target.pace_per_100m_high_s == 107
    # jamais de km/h illisible injecté pour la natation
    assert main.target.pace_low_kmh is None


def test_enrich_covers_interval_set_work_and_rest():
    workout = Workout(
        warmup=_plain_block(600, "Z1"),
        main=[
            IntervalSet(
                reps=4,
                work=IntervalBlock(duration_s=300, target=IntervalTarget(label="Z4", rpe=8)),
                rest=IntervalBlock(duration_s=120, target=IntervalTarget(label="Z1", rpe=2)),
            )
        ],
        cooldown=_plain_block(600, "Z1"),
        summary_md="ok",
    )
    out = enrich_workout_targets(workout, athlete={"fc_max_bpm": 190}, sport="run")
    s = out.main[0]
    assert isinstance(s, IntervalSet)
    assert s.work.target.bpm_low == round(0.80 * 190)
    assert s.rest.target.bpm_low == round(0.50 * 190)


def test_enrich_preserves_llm_provided_values():
    workout = Workout(
        warmup=_plain_block(600, "Z1"),
        main=[
            IntervalBlock(
                duration_s=2400,
                target=IntervalTarget(label="Z2", rpe=4, bpm_low=120, bpm_high=140),
            )
        ],
        cooldown=_plain_block(600, "Z1"),
        summary_md="ok",
    )
    out = enrich_workout_targets(workout, athlete={"fc_max_bpm": 195}, sport="run")
    main = out.main[0]
    assert isinstance(main, IntervalBlock)
    assert main.target.bpm_low == 120
    assert main.target.bpm_high == 140


def test_enrich_degrades_gracefully_without_profile_data():
    out = enrich_workout_targets(_plain_workout(), athlete={}, sport="run")
    main = out.main[0]
    assert isinstance(main, IntervalBlock)
    assert main.target.bpm_low is None
    assert main.target.pace_low_kmh is None


def test_enrich_does_not_mutate_input():
    workout = _plain_workout()
    enrich_workout_targets(workout, athlete={"fc_max_bpm": 195}, sport="run")
    main = workout.main[0]
    assert isinstance(main, IntervalBlock)
    assert main.target.bpm_low is None


def test_describe_session_envelope_states_numeric_bounds():
    text = describe_session_envelope({"session_type": "endurance", "target_duration_s": 3600})
    # warmup eff 486s, cooldown eff 324s, main >= 75%, fenêtre 54-66 min (±10%)
    assert "8min" in text
    assert "5min" in text
    assert "75%" in text
    assert "54" in text
    assert "66" in text


def test_describe_session_envelope_recovery_tighter_caps():
    # recovery 2400s : budget int(0.2*2100)=419 ; warmup int(419*0.6)=251 -> 4min
    # cooldown 419-251=168 -> 2min
    text = describe_session_envelope({"session_type": "recovery", "target_duration_s": 2400})
    assert "4min" in text
    assert "2min" in text
    assert "80%" in text


def test_target_minimal_z_label_only():
    t = IntervalTarget(label="Z2", rpe=5)
    assert t.label == "Z2"
    assert t.bpm_low is None


def test_target_with_bpm_range():
    t = IntervalTarget(label="Z3", bpm_low=145, bpm_high=160, rpe=6)
    assert t.bpm_high == 160


def test_target_with_cadence_range():
    t = IntervalTarget(label="Z2", rpe=5, cadence_low=100, cadence_high=110)
    assert t.cadence_low == 100
    assert t.cadence_high == 110


def test_target_cadence_defaults_to_none():
    t = IntervalTarget(label="Z2", rpe=5)
    assert t.cadence_low is None
    assert t.cadence_high is None


def test_target_rejects_negative_cadence():
    with pytest.raises(ValidationError):
        IntervalTarget(label="Z2", rpe=5, cadence_low=-1)
    with pytest.raises(ValidationError):
        IntervalTarget(label="Z2", rpe=5, cadence_high=-1)


def test_target_rpe_out_of_range_rejects():
    with pytest.raises(ValidationError):
        IntervalTarget(label="Z2", rpe=11)


def test_workout_minimal_structure():
    target = IntervalTarget(label="Z2", rpe=4)
    warmup = IntervalBlock(duration_s=300, target=target)
    main = IntervalBlock(duration_s=1500, target=target)
    cooldown = IntervalBlock(duration_s=300, target=target)
    w = Workout(
        warmup=warmup,
        main=[main],
        cooldown=cooldown,
        summary_md="Test session",
    )
    assert w.summary_md == "Test session"
    assert len(w.main) == 1


def test_workout_intervals_set():
    target_z3 = IntervalTarget(label="Z3", rpe=6)
    target_z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=480, target=target_z3)
    rest = IntervalBlock(duration_s=120, target=target_z1)
    set_ = IntervalSet(reps=4, work=work, rest=rest)
    w = Workout(
        warmup=IntervalBlock(duration_s=600, target=target_z1),
        main=[set_],
        cooldown=IntervalBlock(duration_s=600, target=target_z1),
        summary_md="4x8min threshold",
    )
    assert isinstance(w.main[0], IntervalSet)
    assert w.main[0].reps == 4


def test_workout_reps_bounds():
    target = IntervalTarget(label="Z3", rpe=5)
    block = IntervalBlock(duration_s=120, target=target)
    with pytest.raises(ValidationError):
        IntervalSet(reps=0, work=block, rest=block)
    with pytest.raises(ValidationError):
        IntervalSet(reps=21, work=block, rest=block)


def test_workout_total_duration_includes_sets():
    target = IntervalTarget(label="Z2", rpe=4)
    warmup = IntervalBlock(duration_s=600, target=target)
    cooldown = IntervalBlock(duration_s=600, target=target)
    work = IntervalBlock(duration_s=300, target=target)
    rest = IntervalBlock(duration_s=120, target=target)
    main_set = IntervalSet(reps=5, work=work, rest=rest)
    w = Workout(warmup=warmup, main=[main_set], cooldown=cooldown, summary_md="x")
    # 600 + 5*(300+120) + 600 = 600 + 2100 + 600 = 3300
    assert w.total_duration_s() == 3300


def test_workout_rejects_too_much_warmup_and_cooldown():
    target_z2 = IntervalTarget(label="Z2", rpe=4)
    target_z1 = IntervalTarget(label="Z1", rpe=2)

    # Le modèle se construit, mais la validation par type rejette une structure
    # où l'échauffement + le retour au calme écrasent le corps principal.
    workout = Workout(
        warmup=IntervalBlock(duration_s=900, target=target_z1),
        main=[IntervalBlock(duration_s=1080, target=target_z2)],
        cooldown=IntervalBlock(duration_s=720, target=target_z1),
        summary_md="45min with too little real work",
    )

    with pytest.raises(ValueError, match=r"exceeds cap|main work below"):
        validate_workout_for_session(
            workout, {"target_duration_s": 2700, "session_type": "endurance"}
        )


def test_validate_workout_for_session_accepts_close_duration():
    # endurance effective caps @3000s : warmup<=405s, cooldown<=270s
    target = IntervalTarget(label="Z2", rpe=4)
    workout = Workout(
        warmup=IntervalBlock(duration_s=300, target=target),
        main=[IntervalBlock(duration_s=2400, target=target)],
        cooldown=IntervalBlock(duration_s=270, target=target),
        summary_md="Endurance réaliste",
    )

    validated = validate_workout_for_session(workout, {"target_duration_s": 3000})

    assert validated is workout


def test_validate_workout_for_session_rejects_duration_far_from_target():
    # endurance effective caps @1800s : warmup<=270s, cooldown<=180s
    target = IntervalTarget(label="Z2", rpe=4)
    workout = Workout(
        warmup=IntervalBlock(duration_s=270, target=target),
        main=[IntervalBlock(duration_s=2400, target=target)],
        cooldown=IntervalBlock(duration_s=180, target=target),
        summary_md="Too long",
    )

    with pytest.raises(ValueError, match="too far from target"):
        validate_workout_for_session(workout, {"target_duration_s": 1800})


def _block(dur_s, zone="Z2", rpe=4):
    return {"duration_s": dur_s, "target": {"label": zone, "rpe": rpe}}


def test_structure_caps_endurance():
    caps = structure_caps_for_type("endurance")
    assert caps.warmup_max_s == 15 * 60
    assert caps.cooldown_max_s == 10 * 60
    assert caps.main_min_ratio == 0.75


def test_long_session_rejects_huge_warmup():
    wk = Workout(
        warmup=_block(30 * 60),
        main=[_block(80 * 60)],
        cooldown=_block(10 * 60),
        summary_md="x",
    )
    with pytest.raises(ValueError, match="warmup"):
        validate_workout_for_session(
            wk, {"target_duration_s": 120 * 60, "session_type": "endurance"}
        )


def test_absolute_floor_rejects_too_short_endurance():
    wk = Workout(warmup=_block(60), main=[_block(15 * 60)], cooldown=_block(60), summary_md="x")
    with pytest.raises(ValueError, match="too short"):
        validate_workout_for_session(
            wk, {"target_duration_s": 17 * 60, "session_type": "endurance"}
        )


def test_envelope_for_session_endurance_effective_caps():
    env = envelope_for_session({"session_type": "endurance", "target_duration_s": 3600})
    # budget = int(0.25 * (3600 - 360)) = 810 ; warmup = int(810 * 0.6) = 486 ; cooldown = 324
    assert env.warmup_max_s == 486
    assert env.cooldown_max_s == 324
    assert env.main_min_ratio == 0.75
    assert env.tolerance_s == 360


def test_envelope_caps_bounded_by_fixed_type_caps():
    # Séance très longue : le budget dépasse les caps fixes, qui restent la borne.
    env = envelope_for_session({"session_type": "endurance", "target_duration_s": 14400})
    assert env.warmup_max_s == 900
    assert env.cooldown_max_s == 600


def test_structure_caps_pma():
    caps = structure_caps_for_type("pma")
    assert caps.warmup_max_s == 20 * 60
    assert caps.cooldown_max_s == 15 * 60
    assert caps.main_min_ratio == 0.35
    assert caps.floor_s == 30 * 60


def test_structure_caps_sprint():
    caps = structure_caps_for_type("sprint")
    assert caps.warmup_max_s == 15 * 60
    assert caps.cooldown_max_s == 10 * 60
    assert caps.main_min_ratio == 0.25
    assert caps.floor_s == 25 * 60


def test_sprint_example_workout_passes_validation():
    """Régression : la séance sprint 10x10s/90s (exemple qui a motivé cette feature)
    doit être satisfiable par l'enveloppe de validation pour une cible ~45min."""
    session = {"session_type": "sprint", "target_duration_s": 2700}
    z5 = IntervalTarget(label="Z5", rpe=10)
    z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=10, target=z5)
    rest = IntervalBlock(duration_s=90, target=z1)
    sprint_set = IntervalSet(reps=10, work=work, rest=rest)
    workout = Workout(
        warmup=IntervalBlock(duration_s=850, target=z1),
        main=[sprint_set],
        cooldown=IntervalBlock(duration_s=600, target=z1),
        summary_md="10x10s à fond",
    )
    assert validate_workout_for_session(workout, session) is workout


def test_pma_example_workout_passes_validation():
    """Régression : la séance PMA 5x1min30 (exemple qui a motivé cette feature)
    doit être satisfiable par l'enveloppe de validation pour une cible ~45min."""
    session = {"session_type": "pma", "target_duration_s": 2700}
    z4 = IntervalTarget(label="Z4", rpe=9)
    z1 = IntervalTarget(label="Z1", rpe=2)
    work = IntervalBlock(duration_s=90, target=z4)
    rest = IntervalBlock(duration_s=90, target=z1)
    pma_set = IntervalSet(reps=5, work=work, rest=rest)
    workout = Workout(
        warmup=IntervalBlock(duration_s=930, target=z1),
        main=[pma_set],
        cooldown=IntervalBlock(duration_s=620, target=z1),
        summary_md="5x1min30 PMA",
    )
    assert validate_workout_for_session(workout, session) is workout


@pytest.mark.parametrize(
    ("session_type", "target_s"),
    [
        ("recovery", 2400),
        ("endurance", 3600),
        ("endurance", 2700),
        ("long", 7200),
        ("threshold", 3600),
        ("intervals", 3600),
        ("pma", 2700),
        ("sprint", 2700),
        ("unknown", 3000),
    ],
)
def test_workout_following_announced_caps_passes_validation(session_type, target_s):
    """Anti-régression bug prod 2026-07-03 : un workout qui suit exactement les bornes
    annoncées au LLM (warmup/cooldown au max, total = cible) doit passer la validation."""
    session = {"session_type": session_type, "target_duration_s": target_s}
    env = envelope_for_session(session)
    workout = Workout(
        warmup=_block(env.warmup_max_s, "Z1", 2),
        main=[_block(target_s - env.warmup_max_s - env.cooldown_max_s)],
        cooldown=_block(env.cooldown_max_s, "Z1", 2),
        summary_md="x",
    )
    assert validate_workout_for_session(workout, session) is workout


def test_envelope_prompt_announces_combined_budget():
    text = describe_session_envelope({"session_type": "endurance", "target_duration_s": 3600})
    assert "8min" in text  # warmup 486s -> 8min
    assert "5min" in text  # cooldown 324s -> 5min
    assert "13min au total" in text  # budget combiné 810s -> 13min
    assert "75%" in text


@pytest.mark.parametrize(
    ("session_type", "target_s"),
    [
        ("recovery", 1300),  # target-tol sous le floor : lo doit être clampé au floor
        ("endurance", 3270),  # floor-division 49min serait hors tolérance (330 > 327)
        ("endurance", 2450),  # borne basse proche de la limite du ratio
    ],
)
def test_workout_at_announced_low_bound_passes_validation(session_type, target_s):
    """La borne basse de durée annoncée au LLM doit toujours être satisfiable."""
    session = {"session_type": session_type, "target_duration_s": target_s}
    text = describe_session_envelope(session)
    lo_s = int(re.search(r"entre (\d+)min", text).group(1)) * 60
    env = envelope_for_session(session)
    workout = Workout(
        warmup=_block(env.warmup_max_s, "Z1", 2),
        main=[_block(lo_s - env.warmup_max_s - env.cooldown_max_s)],
        cooldown=_block(env.cooldown_max_s, "Z1", 2),
        summary_md="x",
    )
    assert validate_workout_for_session(workout, session) is workout
