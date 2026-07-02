import pytest
from pydantic import ValidationError

from garmin_sync.coach.workout_schema import (
    IntervalBlock,
    IntervalSet,
    IntervalTarget,
    Workout,
    describe_session_envelope,
    structure_caps_for_type,
    validate_workout_for_session,
)


def test_describe_session_envelope_states_numeric_bounds():
    text = describe_session_envelope({"session_type": "endurance", "target_duration_s": 3600})
    # warmup cap 900s, cooldown cap 600s, main >= 80%, window 54-66 min (±10%, min ±5min)
    assert "15min" in text  # warmup max 900s
    assert "10min" in text  # cooldown max 600s
    assert "80%" in text  # main min ratio
    assert "54" in text  # duration window low bound (min)
    assert "66" in text  # duration window high bound (min)


def test_describe_session_envelope_recovery_tighter_caps():
    text = describe_session_envelope({"session_type": "recovery", "target_duration_s": 2400})
    assert "5min" in text  # warmup + cooldown caps 300s
    assert "90%" in text


def test_target_minimal_z_label_only():
    t = IntervalTarget(label="Z2", rpe=5)
    assert t.label == "Z2"
    assert t.bpm_low is None


def test_target_with_bpm_range():
    t = IntervalTarget(label="Z3", bpm_low=145, bpm_high=160, rpe=6)
    assert t.bpm_high == 160


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
    target = IntervalTarget(label="Z2", rpe=4)
    workout = Workout(
        warmup=IntervalBlock(duration_s=300, target=target),
        main=[IntervalBlock(duration_s=2400, target=target)],
        cooldown=IntervalBlock(duration_s=300, target=target),
        summary_md="Endurance réaliste",
    )

    validated = validate_workout_for_session(workout, {"target_duration_s": 3000})

    assert validated is workout


def test_validate_workout_for_session_rejects_duration_far_from_target():
    target = IntervalTarget(label="Z2", rpe=4)
    workout = Workout(
        warmup=IntervalBlock(duration_s=300, target=target),
        main=[IntervalBlock(duration_s=2400, target=target)],
        cooldown=IntervalBlock(duration_s=300, target=target),
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
    assert caps.main_min_ratio == 0.80


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
