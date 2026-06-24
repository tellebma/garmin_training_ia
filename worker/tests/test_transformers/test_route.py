"""Tests for GPS route downsampling."""

from __future__ import annotations

from garmin_sync.transformers.route import build_route_polyline


def _sample(lat: float | None, lon: float | None) -> dict[str, float | None]:
    return {"latitude": lat, "longitude": lon}


def test_build_route_polyline_returns_lng_lat_pairs() -> None:
    samples = [_sample(45.1, 4.1), _sample(45.2, 4.2)]
    poly = build_route_polyline(samples)
    assert poly == [[4.1, 45.1], [4.2, 45.2]]


def test_build_route_polyline_none_when_under_two_points() -> None:
    assert build_route_polyline([_sample(45.1, 4.1)]) is None
    assert build_route_polyline([_sample(None, None), _sample(45.1, 4.1)]) is None


def test_build_route_polyline_skips_points_without_coords() -> None:
    samples = [_sample(45.1, 4.1), _sample(None, 4.2), _sample(45.3, 4.3)]
    poly = build_route_polyline(samples)
    assert poly == [[4.1, 45.1], [4.3, 45.3]]


def test_build_route_polyline_downsamples_to_64_keeping_ends() -> None:
    samples = [_sample(45.0 + i / 1000, 4.0 + i / 1000) for i in range(500)]
    poly = build_route_polyline(samples)
    assert poly is not None
    assert len(poly) == 64
    assert poly[0] == [4.0, 45.0]
    assert poly[-1] == [round(4.0 + 499 / 1000, 6), round(45.0 + 499 / 1000, 6)]
