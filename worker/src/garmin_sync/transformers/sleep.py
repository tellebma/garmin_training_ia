"""Transform a Garmin sleep payload into a `sleep` row."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def transform_sleep(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    dto = raw.get("dailySleepDTO") or {}
    scores = raw.get("sleepScores") or {}
    return {
        "user_id": user_id,
        "date": dto.get("calendarDate"),
        "sleep_duration_s": dto.get("sleepTimeSeconds"),
        "sleep_score": (scores.get("overall") or {}).get("value"),
        "deep_sleep_s": dto.get("deepSleepSeconds"),
        "light_sleep_s": dto.get("lightSleepSeconds"),
        "rem_sleep_s": dto.get("remSleepSeconds"),
        "awake_s": dto.get("awakeSleepSeconds"),
        "bedtime": _ms_to_iso(dto.get("sleepStartTimestampGMT")),
        "wake_time": _ms_to_iso(dto.get("sleepEndTimestampGMT")),
        "raw": raw,
    }
