from __future__ import annotations

from garmin_sync.coach.geo import haversine_m


def test_haversine_zero_distance_for_identical_points() -> None:
    assert haversine_m(45.0, 6.0, 45.0, 6.0) == 0.0


def test_haversine_known_distance_paris_lyon() -> None:
    # Paris (48.8566, 2.3522) -> Lyon (45.7640, 4.8357) is ~391 km great-circle.
    distance = haversine_m(48.8566, 2.3522, 45.7640, 4.8357)
    assert 385_000 < distance < 400_000


def test_haversine_small_distance_near_150m_threshold() -> None:
    # ~0.00135 deg of latitude at the equator-ish scale is close to 150m.
    distance = haversine_m(45.0, 6.0, 45.00135, 6.0)
    assert 140 < distance < 160
