"""Tests for activities transformer: Garmin API JSON → our DB row."""

from __future__ import annotations

from garmin_sync.transformers.activities import transform_activity, transform_activity_samples


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
    assert row["sport"] == "run"
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
    assert row["sport"] == "bike"
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
    assert row["sport"] == "swim"
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


def test_transform_skips_start_time_when_missing() -> None:
    """If startTimeGMT is missing/None, the row's start_time must be None
    rather than crashing.

    Covers activities.py line 11 (the early-return in _parse_dt)."""
    raw = {
        "activityId": 42,
        "activityType": {"typeKey": "running"},
        "duration": 60.0,
        "distance": 200.0,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["start_time"] is None
    assert row["garmin_activity_id"] == 42


def test_transform_coerces_unparseable_numeric_to_none() -> None:
    """If a numeric field comes in as a non-numeric string, _to_int must
    return None instead of crashing the whole transform.

    Covers activities.py lines 54-55 (the TypeError/ValueError catch)."""
    raw = {
        "activityId": 1,
        "startTimeGMT": "2026-05-10 08:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 60.0,
        "averageHR": "n/a",  # Garmin sometimes sends weird strings on incomplete data
        "calories": "lots",
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["hr_avg"] is None
    assert row["calories"] is None


def test_transform_handles_zero_speed() -> None:
    """Zero (or negative) speed must produce a None pace, not crash on a
    division by zero.

    Covers _pace_s_per_km guard."""
    raw = {
        "activityId": 1,
        "startTimeGMT": "2026-05-10 08:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 60.0,
        "averageSpeed": 0.0,
    }
    row = transform_activity(user_id="u1", raw=raw)
    assert row["pace_avg_s_per_km"] is None


def test_transform_activity_samples_from_detail_metrics() -> None:
    raw_details = {
        "activityDetailMetrics": [
            {
                "metrics": [
                    {"key": "directTimestamp", "value": "2026-05-10T07:00:00.000Z"},
                    {"key": "sumElapsedDuration", "value": 0},
                    {"key": "sumDistance", "value": 0},
                    {"key": "directElevation", "value": 120.4},
                    {"key": "directHeartRate", "value": 145},
                    {"key": "directPower", "value": 210},
                    {"key": "directRunCadence", "value": 172},
                    {"key": "directSpeed", "value": 2.9},
                ]
            },
            {
                "metrics": [
                    {"key": "sumElapsedDuration", "value": 60},
                    {"key": "sumDistance", "value": 170},
                    {"key": "directHeartRate", "value": 148},
                ]
            },
        ]
    }

    rows = transform_activity_samples(user_id="u1", garmin_activity_id=123, raw_details=raw_details)

    assert len(rows) == 2
    assert rows[0]["user_id"] == "u1"
    assert rows[0]["garmin_activity_id"] == 123
    assert rows[0]["sample_index"] == 0
    assert rows[0]["sample_time"] == "2026-05-10T07:00:00+00:00"
    assert rows[0]["elapsed_s"] == 0
    assert rows[0]["distance_m"] == 0
    assert rows[0]["elevation_m"] == 120.4
    assert rows[0]["heart_rate_bpm"] == 145
    assert rows[0]["power_w"] == 210
    assert rows[0]["cadence_rpm"] == 172
    assert rows[0]["speed_m_s"] == 2.9
    assert rows[1]["elapsed_s"] == 60
    assert rows[1]["distance_m"] == 170


def test_transform_activity_samples_accepts_direct_sample_dicts() -> None:
    raw_details = {
        "samples": [
            {
                "elapsedSeconds": 30,
                "distanceMeters": 90.5,
                "heartRateBpm": 142,
                "speedMetersPerSecond": 3.1,
            }
        ]
    }

    rows = transform_activity_samples(user_id="u1", garmin_activity_id=123, raw_details=raw_details)

    assert len(rows) == 1
    assert rows[0]["elapsed_s"] == 30
    assert rows[0]["distance_m"] == 90.5
    assert rows[0]["heart_rate_bpm"] == 142
    assert rows[0]["speed_m_s"] == 3.1


def test_transform_activity_samples_skips_rows_without_metric_signal() -> None:
    rows = transform_activity_samples(
        user_id="u1",
        garmin_activity_id=123,
        raw_details={
            "activityDetailMetrics": [
                {"metrics": [{"key": "sumElapsedDuration", "value": 1}]}
            ]
        },
    )

    assert rows == []
