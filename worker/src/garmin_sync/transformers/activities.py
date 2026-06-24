"""Transform a Garmin activity payload into an `activities` row."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from garmin_sync.coach.tss import compute_tss


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Garmin returns "YYYY-MM-DD HH:MM:SS" assumed UTC
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _pace_s_per_km(avg_speed_m_s: float | None) -> float | None:
    if not avg_speed_m_s or avg_speed_m_s <= 0:
        return None
    return round(1000.0 / avg_speed_m_s, 2)


_DETAIL_SAMPLE_KEYS = ("activityDetailMetrics", "metrics", "samples", "chartData")
_TIME_KEYS = ("directTimestamp", "timestamp", "startTimeGMT", "sampleTime")
_ELAPSED_KEYS = ("sumElapsedDuration", "elapsedDuration", "elapsed_s", "elapsedSeconds")
_DISTANCE_KEYS = ("sumDistance", "distance", "distanceMeters")
_ELEVATION_KEYS = ("directElevation", "elevation", "elevationMeters")
_HR_KEYS = ("directHeartRate", "heartRate", "heartRateBpm")
_POWER_KEYS = ("directPower", "power", "watts")
_CADENCE_KEYS = ("directBikeCadence", "directRunCadence", "cadence", "stepsPerMinute")
_SPEED_KEYS = ("directSpeed", "speed", "speedMetersPerSecond")
_LAT_KEYS = ("directLatitude", "latitude")
_LON_KEYS = ("directLongitude", "longitude")


# Garmin returns granular sport types (e.g. "road_biking", "trail_running").
# We normalize to our 5 canonical sports for the planner/dashboard.
_SPORT_RUN = {
    "running",
    "treadmill_running",
    "trail_running",
    "street_running",
    "track_running",
    "virtual_run",
    "indoor_running",
    "obstacle_run",
}
_SPORT_BIKE = {
    "cycling",
    "road_biking",
    "gravel_cycling",
    "indoor_cycling",
    "mountain_biking",
    "virtual_ride",
    "recumbent_cycling",
    "cyclocross",
    "e_bike_mountain",
    "e_bike_fitness",
    "downhill_biking",
    "bmx",
}
_SPORT_SWIM = {
    "lap_swimming",
    "open_water_swimming",
    "pool_swimming",
    "swimming",
}
_SPORT_BRICK = {"multisport", "transition"}


def _normalize_sport(raw_sport: str) -> str:
    """Map Garmin's granular sport types to our canonical 5 (swim/bike/run/brick/race).

    Unknown sports are returned as-is — the caller can decide what to do (the
    frontend uses a generic icon, the planner ignores them for TSS distribution).
    """
    if raw_sport in _SPORT_RUN:
        return "run"
    if raw_sport in _SPORT_BIKE:
        return "bike"
    if raw_sport in _SPORT_SWIM:
        return "swim"
    if raw_sport in _SPORT_BRICK:
        return "brick"
    return raw_sport


def transform_activity(
    *,
    user_id: str,
    raw: dict[str, Any],
    ftp_watts: int | None = None,
    fc_max_bpm: int | None = None,
) -> dict[str, Any]:
    """Convert a Garmin activity dict into our `activities` table row."""
    start = _parse_dt(raw.get("startTimeGMT"))
    activity_type = raw.get("activityType") or {}
    raw_sport = activity_type.get("typeKey", "unknown")
    sport = _normalize_sport(raw_sport)
    duration_s = int(raw.get("duration") or 0)
    power_avg = _to_int(raw.get("averagePower"))
    hr_avg = _to_int(raw.get("averageHR"))
    tss = compute_tss(
        duration_s=duration_s,
        sport=sport,
        power_avg=power_avg,
        hr_avg=hr_avg,
        ftp_watts=ftp_watts,
        fc_max_bpm=fc_max_bpm,
    )
    return {
        "user_id": user_id,
        "garmin_activity_id": int(raw["activityId"]),
        "start_time": start.isoformat() if start else None,
        "sport": sport,
        "sub_sport": activity_type.get("parentTypeId"),
        "duration_s": duration_s,
        "distance_m": float(raw["distance"]) if raw.get("distance") is not None else None,
        "tss": tss,
        "hr_avg": hr_avg,
        "hr_max": _to_int(raw.get("maxHR")),
        "power_avg": power_avg,
        "power_max": _to_int(raw.get("maxPower")),
        "pace_avg_s_per_km": _pace_s_per_km(raw.get("averageSpeed")),
        "elevation_gain_m": _to_int(raw.get("elevationGain")),
        "calories": _to_int(raw.get("calories")),
        "raw": raw,
    }


def transform_activity_samples(
    *,
    user_id: str,
    garmin_activity_id: int,
    raw_details: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract chart samples from Garmin activity details.

    Garmin Connect has changed the exact shape of activity details over time.
    The common shape is `activityDetailMetrics: [{metrics: [{key, value}, ...]}]`;
    this transformer also accepts direct sample dicts for defensive compatibility.
    """
    samples = _sample_rows(raw_details)
    rows: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples):
        normalized = _normalize_sample(sample)
        if not _has_sample_signal(normalized):
            continue
        rows.append(
            {
                "user_id": user_id,
                "garmin_activity_id": garmin_activity_id,
                "sample_index": idx,
                "sample_time": _parse_sample_time(normalized),
                "elapsed_s": _to_float(_first_value(normalized, _ELAPSED_KEYS)),
                "distance_m": _to_float(_first_value(normalized, _DISTANCE_KEYS)),
                "elevation_m": _to_float(_first_value(normalized, _ELEVATION_KEYS)),
                "heart_rate_bpm": _to_int(_first_value(normalized, _HR_KEYS)),
                "power_w": _to_int(_first_value(normalized, _POWER_KEYS)),
                "cadence_rpm": _to_int(_first_value(normalized, _CADENCE_KEYS)),
                "speed_m_s": _to_float(_first_value(normalized, _SPEED_KEYS)),
                "latitude": _to_float(_first_value(normalized, _LAT_KEYS)),
                "longitude": _to_float(_first_value(normalized, _LON_KEYS)),
                "raw": sample,
            }
        )
    return rows


def _sample_rows(raw_details: dict[str, Any]) -> list[dict[str, Any]]:
    for key in _DETAIL_SAMPLE_KEYS:
        value = raw_details.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _normalize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    metrics = sample.get("metrics")
    if not isinstance(metrics, list):
        return sample

    normalized = {k: v for k, v in sample.items() if k != "metrics"}
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        key = metric.get("key") or metric.get("metricKey")
        if isinstance(key, str):
            normalized[key] = metric.get("value")
    return normalized


def _first_value(sample: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = sample.get(key)
        if value is not None:
            return value
    return None


def _parse_sample_time(sample: dict[str, Any]) -> str | None:
    value = _first_value(sample, _TIME_KEYS)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _has_sample_signal(sample: dict[str, Any]) -> bool:
    signal_keys = (
        _DISTANCE_KEYS + _ELEVATION_KEYS + _HR_KEYS + _POWER_KEYS + _CADENCE_KEYS + _SPEED_KEYS
    )
    return any(_first_value(sample, (key,)) is not None for key in signal_keys)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
