"""Transform a Garmin daily stats payload into a `daily_metrics` row."""

from __future__ import annotations

from typing import Any


def body_battery_fields(raw: dict[str, Any]) -> dict[str, int | None]:
    """Extract the three Body Battery columns from a Garmin daily payload.

    Issue #170 — the payload carries both ``bodyBatteryHighestValue`` (the daily
    peak, reached at wake time) and ``bodyBatteryMostRecentValue`` (the level at
    sync time, i.e. late evening, close to the daily floor). ``body_battery_high``
    used to receive the latter, so ``recovery_baselines.body_battery`` and the
    briefing were comparing an end-of-day value against a "high" baseline.

    Shared with ``backfill_body_battery`` so re-deriving the columns from the
    stored ``raw`` payload can never drift from what the sync writes.
    """
    return {
        "body_battery_low": _to_int(raw.get("bodyBatteryLowestValue")),
        "body_battery_high": _to_int(raw.get("bodyBatteryHighestValue")),
        "body_battery_current": _to_int(raw.get("bodyBatteryMostRecentValue")),
    }


def transform_daily(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": raw["calendarDate"],
        "resting_hr": _to_int(raw.get("restingHeartRate")),
        **body_battery_fields(raw),
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
