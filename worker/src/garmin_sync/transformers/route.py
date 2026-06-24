"""Downsample GPS samples into a compact polyline for thumbnails and heatmaps."""

from __future__ import annotations

from typing import Any

_MAX_ROUTE_POINTS = 64


def build_route_polyline(samples: list[dict[str, Any]]) -> list[list[float]] | None:
    """Return a list of ``[lng, lat]`` points (<=64), or ``None`` if too few GPS points.

    Points are rounded to 6 decimals. The first and last GPS points are always kept;
    intermediate points are evenly spaced.
    """
    points = [
        [round(float(s["longitude"]), 6), round(float(s["latitude"]), 6)]
        for s in samples
        if s.get("latitude") is not None and s.get("longitude") is not None
    ]
    if len(points) < 2:
        return None
    if len(points) <= _MAX_ROUTE_POINTS:
        return points
    step = (len(points) - 1) / (_MAX_ROUTE_POINTS - 1)
    return [points[round(i * step)] for i in range(_MAX_ROUTE_POINTS)]
