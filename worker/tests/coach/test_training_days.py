from garmin_sync.coach.training_days import (
    athlete_level,
    cap_niveau,
    cap_volume,
    repos_min,
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
