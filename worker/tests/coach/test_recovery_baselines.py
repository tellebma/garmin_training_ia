from datetime import date, timedelta

import garmin_sync.coach.recovery_baselines as mod


def _series(today: date, values: list[float], *, step: int = 1) -> list[tuple[date, float]]:
    # values[0] is the most recent day (today), going back `step` days each.
    return [(today - timedelta(days=i * step), v) for i, v in enumerate(values)]


def test_constants() -> None:
    assert mod.WINDOW_DAYS == 28
    assert mod.RECENT_DAYS == 7
    assert mod.STABLE_THRESHOLD == 0.05
    assert mod.CONFIDENCE_HIGH == 21
    assert mod.CONFIDENCE_MEDIUM == 10
    assert mod.FRESHNESS_MAX_AGE_DAYS == 2
    assert mod.SLEEP_DURATION_CAP_S == 28800


def test_no_data_is_safe() -> None:
    today = date(2026, 6, 27)
    b = mod.compute_metric_baseline([], today=today, higher_is_better=True)
    assert b["baseline"] is None
    assert b["recent"] is None
    assert b["trend"] == "no_data"
    assert b["confidence"] == "no_data"
    assert b["freshness"] == "no_data"
    assert b["days_covered"] == 0
    assert b["last_date"] is None


def test_higher_is_better_improving() -> None:
    today = date(2026, 6, 27)
    # 28 days at 50, last 7 days bumped to 70 -> recent median > baseline -> improving for HRV
    older = _series(today - timedelta(days=7), [50.0] * 21)
    recent = _series(today, [70.0] * 7)
    b = mod.compute_metric_baseline(recent + older, today=today, higher_is_better=True)
    assert b["trend"] == "improving"
    assert b["confidence"] == "high"  # 28 days covered
    assert b["freshness"] == "fresh"


def test_lower_is_better_inverts_trend() -> None:
    today = date(2026, 6, 27)
    # resting HR: recent higher than baseline -> declining (worse) when lower_is_better
    older = _series(today - timedelta(days=7), [50.0] * 21)
    recent = _series(today, [60.0] * 7)
    b = mod.compute_metric_baseline(recent + older, today=today, higher_is_better=False)
    assert b["trend"] == "declining"


def test_stable_within_threshold() -> None:
    today = date(2026, 6, 27)
    samples = _series(today, [50.0] * 14)  # recent == baseline
    b = mod.compute_metric_baseline(samples, today=today, higher_is_better=True)
    assert b["trend"] == "stable"


def test_confidence_tiers() -> None:
    today = date(2026, 6, 27)
    low = mod.compute_metric_baseline(
        _series(today, [50.0] * 5), today=today, higher_is_better=True
    )
    med = mod.compute_metric_baseline(
        _series(today, [50.0] * 12), today=today, higher_is_better=True
    )
    assert low["confidence"] == "low"
    assert med["confidence"] == "medium"


def test_freshness_stale_when_old() -> None:
    today = date(2026, 6, 27)
    # last sample 5 days ago
    samples = _series(today - timedelta(days=5), [50.0] * 10)
    b = mod.compute_metric_baseline(samples, today=today, higher_is_better=True)
    assert b["freshness"] == "stale"


def test_baseline_zero_is_stable() -> None:
    today = date(2026, 6, 27)
    samples = _series(today, [0.0] * 10)
    b = mod.compute_metric_baseline(samples, today=today, higher_is_better=True)
    assert b["trend"] == "stable"


def test_sleep_combines_duration_and_score() -> None:
    today = date(2026, 6, 27)
    dur = _series(today, [28800.0] * 14)  # 8h -> normalized 1.0
    score = _series(today, [90.0] * 14)
    b = mod.compute_sleep_baseline(dur, score, today=today)
    assert b["duration_baseline_s"] == 28800
    assert b["score_baseline"] == 90
    assert b["trend"] == "stable"
    assert b["confidence"] == "medium"  # 14 days
