"""Transform a Garmin body composition payload into a `body_composition` row."""

from __future__ import annotations

from typing import Any


def _g_to_kg(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1000.0, 2)
    except (TypeError, ValueError):
        return None


def transform_body(*, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "date": raw.get("calendarDate"),
        "weight_kg": _g_to_kg(raw.get("weight")),
        "body_fat_pct": raw.get("bodyFat"),
        "muscle_mass_kg": _g_to_kg(raw.get("muscleMass")),
        "bone_mass_kg": _g_to_kg(raw.get("boneMass")),
        "body_water_pct": raw.get("bodyWater"),
        "visceral_fat": raw.get("visceralFat"),
        "bmi": raw.get("bmi"),
        "raw": raw,
    }
