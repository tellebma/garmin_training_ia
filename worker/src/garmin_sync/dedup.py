"""Garmin-priority dedup rule for Strava-sourced activities (E15.1).

Many athletes have Garmin auto-exporting to Strava. When both sources are
connected, the same physical activity can arrive twice. V1 rule: Garmin wins
— before inserting a Strava activity we check whether a Garmin activity
already exists for the same user, same normalized sport, and a start_time
within +/-5 minutes. If so, the Strava activity is silently dropped.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

_WINDOW = timedelta(minutes=5)


def is_likely_garmin_duplicate(db: Any, *, user_id: str, start_time: str, sport: str) -> bool:
    parsed = datetime.fromisoformat(start_time)
    window_start = (parsed - _WINDOW).isoformat()
    window_end = (parsed + _WINDOW).isoformat()
    response = (
        db.table("activities")
        .select("id")
        .eq("user_id", user_id)
        .eq("sport", sport)
        .gte("start_time", window_start)
        .lte("start_time", window_end)
        .execute()
    )
    rows = response.data or []
    return len(rows) > 0
