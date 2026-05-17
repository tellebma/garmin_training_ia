from __future__ import annotations

from garmin_sync.transformers.body import transform_body


def test_transform_body_full() -> None:
    raw = {
        "calendarDate": "2026-05-15",
        "weight": 72500,
        "bodyFat": 14.2,
        "muscleMass": 35200,
        "boneMass": 3100,
        "bodyWater": 60.5,
        "visceralFat": 8.0,
        "bmi": 22.4,
    }
    row = transform_body(user_id="u1", raw=raw)
    assert row["weight_kg"] == 72.5
    assert row["body_fat_pct"] == 14.2
    assert row["muscle_mass_kg"] == 35.2
    assert row["bmi"] == 22.4
