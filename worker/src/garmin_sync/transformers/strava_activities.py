"""Transform a Strava activity payload into an `activities` row."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from garmin_sync.coach.tss import compute_tss

_SPORT_RUN = {"run", "trailrun", "virtualrun"}
_SPORT_BIKE = {
    "ride",
    "virtualride",
    "gravelride",
    "mountainbikeride",
    "ebikeride",
    "velomobile",
    "handcycle",
}
_SPORT_SWIM = {"swim"}
_SPORT_BRICK = {"multisport"}


def _normalize_sport(raw_type: str) -> str:
    """Map Strava's `type`/`sport_type` (PascalCase, e.g. "Run") to our 5
    canonical sports. Unknown types pass through lower-cased, same contract
    as the Garmin transformer's `_normalize_sport`."""
    key = raw_type.lower()
    if key in _SPORT_RUN:
        return "run"
    if key in _SPORT_BIKE:
        return "bike"
    if key in _SPORT_SWIM:
        return "swim"
    if key in _SPORT_BRICK:
        return "brick"
    return key


def _pace_s_per_km(avg_speed_m_s: float | None) -> float | None:
    if not avg_speed_m_s or avg_speed_m_s <= 0:
        return None
    return round(1000.0 / avg_speed_m_s, 2)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def transform_strava_activity(
    *,
    user_id: str,
    raw: dict[str, Any],
    ftp_watts: int | None = None,
    fc_max_bpm: int | None = None,
) -> dict[str, Any]:
    """Convert a Strava activity dict into our `activities` table row."""
    raw_sport = raw.get("sport_type") or raw.get("type") or "unknown"
    sport = _normalize_sport(raw_sport)
    duration_s = int(raw.get("elapsed_time") or 0)
    power_avg = _to_int(raw.get("average_watts"))
    hr_avg = _to_int(raw.get("average_heartrate"))
    tss = compute_tss(
        duration_s=duration_s,
        sport=sport,
        power_avg=power_avg,
        hr_avg=hr_avg,
        ftp_watts=ftp_watts,
        fc_max_bpm=fc_max_bpm,
    )
    start_date = raw.get("start_date")
    start_time = (
        datetime.fromisoformat(start_date.replace("Z", "+00:00")).isoformat()
        if start_date
        else None
    )
    return {
        "user_id": user_id,
        "source": "strava",
        "strava_activity_id": int(raw["id"]),
        "garmin_activity_id": None,
        "start_time": start_time,
        "sport": sport,
        "sub_sport": None,
        "duration_s": duration_s,
        "distance_m": float(raw["distance"]) if raw.get("distance") is not None else None,
        "tss": tss,
        "hr_avg": hr_avg,
        "hr_max": _to_int(raw.get("max_heartrate")),
        "power_avg": power_avg,
        "power_max": _to_int(raw.get("max_watts")),
        "pace_avg_s_per_km": _pace_s_per_km(raw.get("average_speed")),
        "elevation_gain_m": _to_int(raw.get("total_elevation_gain")),
        "calories": _to_int(raw.get("calories")),
        "raw": raw,
    }
