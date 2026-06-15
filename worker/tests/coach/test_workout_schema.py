import pytest
from pydantic import ValidationError

from garmin_sync.coach.workout_schema import (
    IntervalBlock,
    IntervalSet,
    IntervalTarget,
    Workout,
    validate_workout_for_session,
)


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

    with pytest.raises(ValidationError):
        Workout(
            warmup=IntervalBlock(duration_s=900, target=target_z1),
            main=[IntervalBlock(duration_s=1080, target=target_z2)],
            cooldown=IntervalBlock(duration_s=720, target=target_z1),
            summary_md="45min with too little real work",
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
