from __future__ import annotations

from garmin_sync.transformers.daily import transform_daily


def test_transform_daily_full_payload() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": 52,
        "bodyBatteryMostRecentValue": 78,
        "bodyBatteryLowestValue": 23,
        "averageStressLevel": 35,
        "totalSteps": 12500,
        "activeKilocalories": 850,
        "totalKilocalories": 2400,
    }
    row = transform_daily(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["resting_hr"] == 52
    assert row["body_battery_high"] == 78
    assert row["body_battery_low"] == 23
    assert row["stress_avg"] == 35
    assert row["steps"] == 12500


def test_transform_daily_missing_fields() -> None:
    raw = {"calendarDate": "2026-05-15"}
    row = transform_daily(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["resting_hr"] is None
    assert row["steps"] is None
