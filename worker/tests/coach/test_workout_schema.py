import re

import pytest
from pydantic import ValidationError

from garmin_sync.coach.workout_schema import (
    IntervalBlock,
    IntervalSet,
    IntervalTarget,
    Workout,
    describe_session_envelope,
    envelope_for_session,
    structure_caps_for_type,
    validate_workout_for_session,
)


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


@pytest.mark.parametrize(
    ("session_type", "target_s"),
    [
        ("recovery", 2400),
        ("endurance", 3600),
        ("endurance", 2700),
        ("long", 7200),
        ("threshold", 3600),
        ("intervals", 3600),
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
