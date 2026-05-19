from __future__ import annotations

from garmin_sync.transformers.hrv import transform_hrv


def test_transform_hrv_full() -> None:
    raw = {
        "hrvSummary": {
            "calendarDate": "2026-05-15",
            "lastNightAvg": 54.3,
            "status": "BALANCED",
            "weeklyAvg": 52.1,
        },
        "hrvReadings": [],
    }
    row = transform_hrv(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["hrv_rmssd"] == 54.3
    assert row["hrv_status"] == "balanced"
    assert row["hrv_weekly_avg"] == 52.1


def test_transform_hrv_no_summary() -> None:
    raw = {"hrvReadings": []}
    row = transform_hrv(user_id="u1", raw=raw)
    assert row["date"] is None
    assert row["hrv_rmssd"] is None
    assert row["hrv_status"] is None
