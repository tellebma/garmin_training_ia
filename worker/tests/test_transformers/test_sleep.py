from __future__ import annotations

from garmin_sync.transformers.sleep import transform_sleep


def test_transform_sleep() -> None:
    raw = {
        "dailySleepDTO": {
            "calendarDate": "2026-05-15",
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 7200,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 5400,
            "awakeSleepSeconds": 1800,
            "sleepStartTimestampGMT": 1715900400000,
            "sleepEndTimestampGMT": 1715929200000,
        },
        "sleepScores": {"overall": {"value": 82}},
    }
    row = transform_sleep(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["sleep_duration_s"] == 28800
    assert row["sleep_score"] == 82
    assert row["deep_sleep_s"] == 7200
