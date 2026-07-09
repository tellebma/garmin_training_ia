"""Overpass API (OpenStreetMap) client — refresh the shared `cols` reference table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx

from garmin_sync.coach.geo import haversine_m
from garmin_sync.supabase_client import get_admin_client

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_RADIUS_M = 50_000
_TIMEOUT_S = 30.0
_CACHE_MAX_AGE_DAYS = 30
_CACHE_MOVE_THRESHOLD_M = 5_000
# Overpass rejects requests without an identifying User-Agent (406 Not Acceptable),
# per its usage policy: https://operations.osmfoundation.org/policies/overpass/
_HEADERS = {"User-Agent": "garmin-training-coach/1.0 (github.com/tellebma/garmin_training_ia)"}


def _now() -> datetime:
    return datetime.now(UTC)


def _build_query(home_lat: float, home_lon: float) -> str:
    return (
        "[out:json][timeout:25];"
        f"node[mountain_pass=yes](around:{_RADIUS_M},{home_lat},{home_lon});"
        "out;"
    )


def _parse_elevation(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return round(float(raw))
    except (TypeError, ValueError):
        return None


def _should_refresh(profile: dict[str, Any], home_lat: float, home_lon: float) -> bool:
    updated_at = profile.get("cols_cache_updated_at")
    if not updated_at:
        return True
    fetched = datetime.fromisoformat(str(updated_at))
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    if _now() - fetched > timedelta(days=_CACHE_MAX_AGE_DAYS):
        return True
    cache_lat = profile.get("cols_cache_home_lat")
    cache_lon = profile.get("cols_cache_home_lon")
    if cache_lat is None or cache_lon is None:
        return True
    moved_m = haversine_m(float(cache_lat), float(cache_lon), home_lat, home_lon)
    return moved_m > _CACHE_MOVE_THRESHOLD_M


def refresh_nearby_cols(user_id: str, home_lat: float, home_lon: float) -> None:
    """Refresh the shared `cols` cache from Overpass if stale or the user moved."""
    db = get_admin_client()
    profile_resp = (
        db.table("athlete_profiles")
        .select("cols_cache_updated_at, cols_cache_home_lat, cols_cache_home_lon")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    profile = cast("dict[str, Any] | None", profile_resp.data if profile_resp else None)
    if profile is not None and not _should_refresh(profile, home_lat, home_lon):
        return

    response = httpx.get(
        _OVERPASS_URL,
        params={"data": _build_query(home_lat, home_lon)},
        headers=_HEADERS,
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    elements = response.json().get("elements", [])

    rows = [
        {
            "osm_id": element["id"],
            "name": element.get("tags", {}).get("name") or f"Col (OSM #{element['id']})",
            "latitude": element["lat"],
            "longitude": element["lon"],
            "elevation_m": _parse_elevation(element.get("tags", {}).get("ele")),
            "fetched_at": _now().isoformat(),
        }
        for element in elements
        if element.get("type") == "node" and "lat" in element and "lon" in element
    ]
    if rows:
        db.table("cols").upsert(rows, on_conflict="osm_id").execute()

    db.table("athlete_profiles").update(
        {
            "cols_cache_updated_at": _now().isoformat(),
            "cols_cache_home_lat": home_lat,
            "cols_cache_home_lon": home_lon,
        }
    ).eq("user_id", user_id).execute()
