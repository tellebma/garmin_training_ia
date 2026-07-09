from garmin_sync.coach.duration_bounds import clamp_duration_to_bounds, duration_bounds_s


def test_bike_endurance_base_floor_is_90min():
    low, high = duration_bounds_s("bike", "endurance", "base")
    assert low == 90 * 60
    assert high == 180 * 60


def test_clamp_raises_short_bike_endurance_to_floor():
    assert clamp_duration_to_bounds("bike", "endurance", "base", 45 * 60) == 90 * 60


def test_clamp_caps_overlong_run_endurance():
    assert clamp_duration_to_bounds("run", "endurance", "base", 200 * 60) == 60 * 60


def test_clamp_keeps_value_inside_bounds():
    assert clamp_duration_to_bounds("run", "endurance", "base", 50 * 60) == 50 * 60


def test_unknown_combo_returns_value_unchanged():
    assert clamp_duration_to_bounds("brick", "intervals", "base", 30 * 60) == 30 * 60


def test_taper_uses_peak_bounds():
    assert duration_bounds_s("run", "endurance", "taper") == duration_bounds_s(
        "run", "endurance", "peak"
    )


def test_duration_bounds_s_returns_none_for_unknown():
    assert duration_bounds_s("brick", "intervals", "base") is None


def test_bike_sprint_peak_bounds():
    assert duration_bounds_s("bike", "sprint", "peak") == (35 * 60, 45 * 60)


def test_bike_pma_build_bounds():
    assert duration_bounds_s("bike", "pma", "build") == (45 * 60, 65 * 60)


def test_bike_pma_peak_bounds():
    assert duration_bounds_s("bike", "pma", "peak") == (40 * 60, 60 * 60)


def test_run_sprint_peak_bounds():
    assert duration_bounds_s("run", "sprint", "peak") == (25 * 60, 35 * 60)


def test_run_pma_build_bounds():
    assert duration_bounds_s("run", "pma", "build") == (40 * 60, 55 * 60)


def test_swim_sprint_peak_bounds():
    assert duration_bounds_s("swim", "sprint", "peak") == (30 * 60, 40 * 60)


def test_swim_pma_build_bounds():
    assert duration_bounds_s("swim", "pma", "build") == (40 * 60, 55 * 60)


def test_sprint_taper_uses_peak_bounds():
    assert duration_bounds_s("bike", "sprint", "taper") == duration_bounds_s(
        "bike", "sprint", "peak"
    )


def test_clamp_caps_overlong_bike_sprint():
    assert clamp_duration_to_bounds("bike", "sprint", "peak", 90 * 60) == 45 * 60
