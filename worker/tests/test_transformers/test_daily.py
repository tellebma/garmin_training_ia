from __future__ import annotations

from garmin_sync.transformers.daily import body_battery_fields, transform_daily


def test_transform_daily_full_payload() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": 52,
        "bodyBatteryHighestValue": 95,
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
    assert row["body_battery_high"] == 95
    assert row["body_battery_current"] == 78
    assert row["body_battery_low"] == 23
    assert row["stress_avg"] == 35
    assert row["steps"] == 12500


def test_transform_daily_missing_fields() -> None:
    raw = {"calendarDate": "2026-05-15"}
    row = transform_daily(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["resting_hr"] is None
    assert row["steps"] is None


def test_transform_daily_coerces_non_numeric_to_none() -> None:
    """A field arriving as a non-coercible string must produce None instead
    of crashing the row.

    Covers daily.py lines 29-30 (the TypeError/ValueError catch in _to_int)."""
    raw = {
        "calendarDate": "2026-05-15",
        "restingHeartRate": "n/a",
        "totalSteps": "n/a",
    }
    row = transform_daily(user_id="u1", raw=raw)
    assert row["resting_hr"] is None
    assert row["steps"] is None


def test_body_battery_high_is_the_daily_maximum_not_the_last_value() -> None:
    """Issue #170 — real prod payload shape (daily_metrics.raw, 2026-08-14).

    ``bodyBatteryMostRecentValue`` is the level at sync time (late evening, so
    near the daily floor); ``bodyBatteryHighestValue`` is the daily peak. The
    column named ``_high`` must carry the peak, otherwise ``recovery_baselines``
    and the briefing compare an end-of-day value to a "high" baseline.
    """
    raw = {
        "calendarDate": "2026-08-14",
        "bodyBatteryHighestValue": 95,
        "bodyBatteryLowestValue": 26,
        "bodyBatteryMostRecentValue": 26,
        "bodyBatteryDuringSleep": 58,
        "bodyBatteryAtWakeTime": 95,
    }
    assert body_battery_fields(raw) == {
        "body_battery_low": 26,
        "body_battery_high": 95,
        "body_battery_current": 26,
    }


def test_body_battery_fields_tolerate_a_payload_without_body_battery() -> None:
    assert body_battery_fields({"calendarDate": "2026-08-14"}) == {
        "body_battery_low": None,
        "body_battery_high": None,
        "body_battery_current": None,
    }
