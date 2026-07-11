from __future__ import annotations

from garmin_sync.transformers.strava_activities import transform_strava_activity

_RAW_RUN = {
    "id": 987654321,
    "type": "Run",
    "start_date": "2026-07-01T06:30:00Z",
    "elapsed_time": 1800,
    "distance": 5000.0,
    "average_heartrate": 150.0,
    "max_heartrate": 172.0,
    "average_watts": None,
    "max_watts": None,
    "average_speed": 2.78,
    "total_elevation_gain": 42.0,
    "calories": 350,
}


def test_transform_strava_activity_maps_core_fields():
    row = transform_strava_activity(user_id="u1", raw=_RAW_RUN)

    assert row["user_id"] == "u1"
    assert row["source"] == "strava"
    assert row["strava_activity_id"] == 987654321
    assert row["garmin_activity_id"] is None
    assert row["start_time"] == "2026-07-01T06:30:00+00:00"
    assert row["sport"] == "run"
    assert row["duration_s"] == 1800
    assert row["distance_m"] == 5000.0
    assert row["hr_avg"] == 150
    assert row["hr_max"] == 172
    assert row["elevation_gain_m"] == 42
    assert row["calories"] == 350
    assert row["raw"] == _RAW_RUN


def test_transform_strava_activity_maps_ride_to_bike():
    row = transform_strava_activity(user_id="u1", raw={**_RAW_RUN, "type": "Ride", "id": 2})
    assert row["sport"] == "bike"


def test_transform_strava_activity_maps_swim():
    row = transform_strava_activity(user_id="u1", raw={**_RAW_RUN, "type": "Swim", "id": 3})
    assert row["sport"] == "swim"


def test_transform_strava_activity_passes_through_unknown_type():
    row = transform_strava_activity(user_id="u1", raw={**_RAW_RUN, "type": "Yoga", "id": 4})
    assert row["sport"] == "yoga"


def test_transform_strava_activity_tss_falls_back_to_duration_without_power_or_fcmax():
    row = transform_strava_activity(user_id="u1", raw=_RAW_RUN)
    assert row["tss"] == 25.0


def test_transform_strava_activity_computes_hr_tss_with_fcmax():
    row = transform_strava_activity(user_id="u1", raw=_RAW_RUN, fc_max_bpm=190)
    assert row["tss"] is not None
    assert row["tss"] > 0


def test_transform_strava_activity_handles_missing_optional_fields():
    minimal = {"id": 5, "type": "Run", "start_date": "2026-07-01T06:30:00Z", "elapsed_time": 600}
    row = transform_strava_activity(user_id="u1", raw=minimal)
    assert row["distance_m"] is None
    assert row["hr_avg"] is None
    assert row["calories"] is None
