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


def test_transform_body_handles_missing_fields() -> None:
    """A partial Garmin payload (only calendarDate + weight) must not crash."""
    raw = {"calendarDate": "2026-05-15", "weight": 70000}
    row = transform_body(user_id="u1", raw=raw)
    assert row["date"] == "2026-05-15"
    assert row["weight_kg"] == 70.0
    assert row["body_fat_pct"] is None
    assert row["muscle_mass_kg"] is None


def test_transform_body_coerces_non_numeric_weight_to_none() -> None:
    """If a numeric field is sent as a non-coercible string, _g_to_kg must
    return None instead of crashing.

    Covers body.py lines 13-14 (the TypeError/ValueError catch)."""
    raw = {
        "calendarDate": "2026-05-15",
        "weight": "n/a",
        "muscleMass": "n/a",
    }
    row = transform_body(user_id="u1", raw=raw)
    assert row["weight_kg"] is None
    assert row["muscle_mass_kg"] is None
