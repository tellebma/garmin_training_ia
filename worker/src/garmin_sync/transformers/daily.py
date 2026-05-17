"""Transform a Garmin daily stats payload into a `daily_metrics` row."""

from __future__ import annotations

from typing import Any


def transform_daily(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": raw["calendarDate"],
        "resting_hr": _to_int(raw.get("restingHeartRate")),
        "body_battery_low": _to_int(raw.get("bodyBatteryLowestValue")),
        "body_battery_high": _to_int(raw.get("bodyBatteryMostRecentValue")),
        "stress_avg": _to_int(raw.get("averageStressLevel")),
        "steps": _to_int(raw.get("totalSteps")),
        "active_calories": _to_int(raw.get("activeKilocalories")),
        "total_calories": _to_int(raw.get("totalKilocalories")),
        "readiness_score": None,
        "raw": raw,
    }


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
