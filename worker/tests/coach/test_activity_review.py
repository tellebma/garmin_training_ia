from datetime import date

from garmin_sync.coach.activity_review import build_activity_review


def _activity(
    day: str,
    *,
    sport: str = "run",
    duration_s: int = 3600,
    tss: float | None = 50,
    elevation_gain_m: int = 0,
) -> dict:
    return {
        "start_time": f"{day}T08:00:00Z",
        "sport": sport,
        "duration_s": duration_s,
        "tss": tss,
        "elevation_gain_m": elevation_gain_m,
    }


def test_activity_review_detects_load_spike_and_recent_long_session():
    today = date(2026, 5, 20)
    activities = [
        _activity("2026-04-24", tss=90),
        _activity("2026-05-01", tss=90),
        _activity("2026-05-08", tss=90),
        _activity("2026-05-18", sport="bike", duration_s=3 * 3600, tss=120),
        _activity("2026-05-17", sport="run", duration_s=3600, tss=90),
        _activity("2026-05-19", sport="run", duration_s=3600, tss=90),
    ]

    review = build_activity_review(activities, today=today)

    assert review.activities_7d == 3
    assert review.tss_7d == 300
    names = {i.name for i in review.insights}
    assert "load_spike" in names
    assert "recent_long_session" in names
    assert sum(i.readiness_impact for i in review.insights) < 0


def test_activity_review_detects_return_after_break():
    review = build_activity_review(
        [_activity("2026-05-01", sport="run", tss=45)],
        today=date(2026, 5, 20),
    )

    assert review.days_since_last_activity == 19
    assert review.insights[0].name == "return_after_break"
    assert review.insights[0].readiness_impact == -10


def test_activity_review_rewards_consistent_week_without_risk():
    review = build_activity_review(
        [
            _activity("2026-05-14", sport="swim", tss=35),
            _activity("2026-05-16", sport="bike", tss=55),
            _activity("2026-05-18", sport="run", tss=45),
            _activity("2026-05-19", sport="swim", tss=30),
        ],
        today=date(2026, 5, 20),
    )

    assert review.activities_7d == 4
    assert any(i.name == "consistent_week" for i in review.insights)
    assert sum(i.readiness_impact for i in review.insights) > 0


def test_activity_review_serializes_for_api_payload():
    review = build_activity_review([], today=date(2026, 5, 20))
    payload = review.to_dict()

    assert payload["lookback_days"] == 90
    assert payload["activities_7d"] == 0
    assert payload["insights"][0]["name"] == "no_activity_history"
