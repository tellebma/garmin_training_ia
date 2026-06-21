from itertools import pairwise

from garmin_sync.coach.training_days import (
    assign_sports,
    athlete_level,
    cap_niveau,
    cap_volume,
    repos_min,
    run_cap,
    select_training_days,
    training_days_count,
)


def test_cap_volume_by_hours():
    assert cap_volume(4) == 4
    assert cap_volume(6) == 5
    assert cap_volume(8) == 6
    assert cap_volume(10) == 6


def test_athlete_level_from_strengths():
    assert athlete_level({"swim": 1, "bike": 2, "run": 2}) == "beginner"
    assert athlete_level({"swim": 3, "bike": 3, "run": 3}) == "intermediate"
    assert athlete_level({"swim": 4, "bike": 5, "run": 4}) == "advanced"


def test_cap_niveau():
    assert cap_niveau("beginner") == 4
    assert cap_niveau("intermediate") == 5
    assert cap_niveau("advanced") == 6


def test_repos_min_beginner_floor_two():
    assert repos_min("beginner", "base") == 2
    assert repos_min("intermediate", "base") == 1
    assert repos_min("intermediate", "taper") == 2


def test_training_days_count_intermediate_7avail_8h():
    assert training_days_count(n_available=7, hours=8, level="intermediate", phase="build") == 5


def test_training_days_count_beginner_7avail_4h():
    assert training_days_count(n_available=7, hours=4, level="beginner", phase="base") == 4


def test_training_days_count_never_below_one_rest():
    assert training_days_count(n_available=7, hours=12, level="advanced", phase="build") <= 6


def test_select_spreads_days():
    chosen = select_training_days(available_idx={0, 1, 2, 3, 4, 5, 6}, count=5)
    assert len(chosen) == 5
    assert chosen <= {0, 1, 2, 3, 4, 5, 6}


def test_select_count_zero_returns_empty():
    assert select_training_days(available_idx={0, 2, 4}, count=0) == set()


def test_select_count_ge_available_returns_all():
    assert select_training_days(available_idx={0, 2, 4}, count=9) == {0, 2, 4}


def test_run_cap_by_level():
    assert run_cap("beginner") == 2
    assert run_cap("intermediate") == 3
    assert run_cap("advanced") == 4


def test_assign_sports_no_back_to_back_run():
    days = [0, 1, 2, 3, 4]
    assignment = assign_sports(
        training_idx=days, sports_in_race=["swim", "bike", "run"], level="intermediate"
    )
    ordered = [assignment[d] for d in days]
    for a, b in pairwise(ordered):
        assert not (a == "run" and b == "run")


def test_assign_sports_respects_run_cap():
    days = [0, 1, 2, 3, 4, 5]
    assignment = assign_sports(training_idx=days, sports_in_race=["run"], level="beginner")
    assert sum(1 for s in assignment.values() if s == "run") <= run_cap("beginner")
