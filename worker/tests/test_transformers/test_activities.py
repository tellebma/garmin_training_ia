"""Tests for activities transformer: Garmin API JSON → our DB row."""

from __future__ import annotations

from garmin_sync.transformers.activities import transform_activity


def test_transform_basic_running_activity() -> None:
    raw = {
        "activityId": 12345,
        "activityName": "Easy run",
        "startTimeGMT": "2026-05-10 07:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 3600.0,
        "distance": 10000.0,
        "averageHR": 145,
        "maxHR": 168,
        "calories": 700,
        "elevationGain": 50.0,
        "averageSpeed": 2.78,
    }
    user_id = "11111111-1111-1111-1111-111111111111"
    row = transform_activity(user_id=user_id, raw=raw)

    assert row["user_id"] == user_id
    assert row["garmin_activity_id"] == 12345
    assert row["sport"] == "running"
    assert row["duration_s"] == 3600
    assert row["distance_m"] == 10000.0
    assert row["hr_avg"] == 145
    assert row["hr_max"] == 168
    assert row["elevation_gain_m"] == 50
    assert row["calories"] == 700
    assert row["pace_avg_s_per_km"] is not None
    assert 355 <= row["pace_avg_s_per_km"] <= 365
    assert row["raw"] == raw


def test_transform_cycling_with_power() -> None:
    raw = {
        "activityId": 99,
        "startTimeGMT": "2026-05-10 09:00:00",
        "activityType": {"typeKey": "cycling"},
        "duration": 7200.0,
        "distance": 80000.0,
        "averagePower": 220,
        "maxPower": 450,
        "averageHR": 150,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["sport"] == "cycling"
    assert row["power_avg"] == 220
    assert row["power_max"] == 450


def test_transform_swim_no_distance_pace() -> None:
    raw = {
        "activityId": 7,
        "startTimeGMT": "2026-05-10 18:00:00",
        "activityType": {"typeKey": "lap_swimming"},
        "duration": 1800.0,
        "distance": 2000.0,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["sport"] == "lap_swimming"
    assert row["distance_m"] == 2000.0
    assert row["pace_avg_s_per_km"] is None


def test_transform_handles_null_fields_gracefully() -> None:
    raw = {
        "activityId": 1,
        "startTimeGMT": "2026-05-10 08:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 0.0,
        "distance": None,
        "averageHR": None,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["distance_m"] is None
    assert row["hr_avg"] is None
    assert row["duration_s"] == 0
