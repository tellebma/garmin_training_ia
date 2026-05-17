"""Transform a Garmin HRV payload into an `hrv` row."""

from __future__ import annotations

from typing import Any

_ALLOWED_STATUSES = {"balanced", "unbalanced", "low", "poor", "no_status"}


def transform_hrv(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    status_raw = raw.get("status")
    status = (status_raw or "").lower().replace(" ", "_") if status_raw else None
    return {
        "user_id": user_id,
        "date": raw.get("calendarDate"),
        "hrv_rmssd": raw.get("lastNightAvg"),
        "hrv_status": status if status in _ALLOWED_STATUSES else None,
        "hrv_weekly_avg": raw.get("weeklyAvg"),
        "raw": raw,
    }
