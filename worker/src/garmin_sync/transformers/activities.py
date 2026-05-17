"""Transform a Garmin activity payload into an `activities` row."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Garmin returns "YYYY-MM-DD HH:MM:SS" assumed UTC
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _pace_s_per_km(avg_speed_m_s: float | None) -> float | None:
    if not avg_speed_m_s or avg_speed_m_s <= 0:
        return None
    return round(1000.0 / avg_speed_m_s, 2)


def transform_activity(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Garmin activity dict into our `activities` table row.

    Pure function — no I/O. The caller decides whether to insert/upsert.
    """
    start = _parse_dt(raw.get("startTimeGMT"))
    activity_type = raw.get("activityType") or {}
    return {
        "user_id": user_id,
        "garmin_activity_id": int(raw["activityId"]),
        "start_time": start.isoformat() if start else None,
        "sport": activity_type.get("typeKey", "unknown"),
        "sub_sport": activity_type.get("parentTypeId"),
        "duration_s": int(raw.get("duration") or 0),
        "distance_m": float(raw["distance"]) if raw.get("distance") is not None else None,
        "tss": None,  # Garmin doesn't expose TSS directly; computed in E4
        "hr_avg": _to_int(raw.get("averageHR")),
        "hr_max": _to_int(raw.get("maxHR")),
        "power_avg": _to_int(raw.get("averagePower")),
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
