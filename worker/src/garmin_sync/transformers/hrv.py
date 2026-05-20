"""Transform a Garmin HRV payload into an `hrv` row.

Garmin HRV endpoint /hrv-service/hrv/{date} returns a nested shape:

    {
      "userProfilePk": ...,
      "hrvSummary": {
        "calendarDate": "2026-05-19",
        "lastNightAvg": 45,
        "weeklyAvg": 48,
        "status": "BALANCED",
        ...
      },
      "hrvReadings": [...]   # per-5-minute samples we don't store
    }

So all top-level reads go through ``raw["hrvSummary"]``.
"""

from __future__ import annotations

from typing import Any

_ALLOWED_STATUSES = {"balanced", "unbalanced", "low", "poor", "no_status"}


def transform_hrv(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    summary = raw.get("hrvSummary") or {}
    status_raw = summary.get("status")
    status = (status_raw or "").lower().replace(" ", "_") if status_raw else None
    return {
        "user_id": user_id,
        "date": summary.get("calendarDate"),
        "hrv_rmssd": summary.get("lastNightAvg"),
        "hrv_status": status if status in _ALLOWED_STATUSES else None,
        "hrv_weekly_avg": summary.get("weeklyAvg"),
        "raw": raw,
    }
