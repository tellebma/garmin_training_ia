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


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
