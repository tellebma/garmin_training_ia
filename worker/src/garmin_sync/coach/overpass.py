"""Overpass API (OpenStreetMap) client — refresh the shared `cols` reference table."""

from __future__ import annotations

import time
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
_MAX_NAME_LENGTH = 200
_MIN_PEAK_ELEVATION_M = 500
# Overpass rejects requests without an identifying User-Agent (406 Not Acceptable),
# per its usage policy: https://operations.osmfoundation.org/policies/overpass/
_HEADERS = {"User-Agent": "garmin-training-coach/1.0 (github.com/tellebma/garmin_training_ia)"}
# Overpass renvoie 429 quand ses slots par IP sont occupés (vécu en prod 2026-07-26
# pendant le backfill multi-zones) et 504 quand il est surchargé — les deux valent
# un retry patient plutôt qu'un échec du run.
_RETRYABLE_STATUSES = frozenset({429, 504})
_RETRY_DELAYS_S: tuple[float, ...] = (15.0, 45.0, 90.0)


def _overpass_get(query: str) -> Any:
    """GET Overpass avec backoff sur 429/504 ; propage les autres erreurs HTTP."""
    for delay in (*_RETRY_DELAYS_S, None):
        response = httpx.get(
            _OVERPASS_URL,
            params={"data": query},
            headers=_HEADERS,
            timeout=_TIMEOUT_S,
        )
        if response.status_code in _RETRYABLE_STATUSES and delay is not None:
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise AssertionError("unreachable")  # pragma: no cover


def _classify(tags: dict[str, Any]) -> str | None:
    if tags.get("mountain_pass") == "yes":
        return "col"
    if tags.get("natural") == "peak":
        return "peak"
    return None


def _now() -> datetime:
    return datetime.now(UTC)


def _build_query(home_lat: float, home_lon: float) -> str:
    return (
        "[out:json][timeout:25];"
        "("
        f"node[mountain_pass=yes](around:{_RADIUS_M},{home_lat},{home_lon});"
        f"node[natural=peak](around:{_RADIUS_M},{home_lat},{home_lon});"
        ");"
        "out;"
    )


def _build_bbox_query(south: float, west: float, north: float, east: float) -> str:
    bbox = f"{south},{west},{north},{east}"
    return (
        f"[out:json][timeout:25];(node[mountain_pass=yes]({bbox});node[natural=peak]({bbox}););out;"
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


def _element_to_row(element: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Overpass node to a `cols` row, or None if it should be skipped."""
    if element.get("type") != "node" or "lat" not in element or "lon" not in element:
        return None
    tags = element.get("tags", {})
    col_type = _classify(tags)
    if col_type is None:
        return None
    elevation_m = _parse_elevation(tags.get("ele"))
    if col_type == "peak" and (elevation_m is None or elevation_m < _MIN_PEAK_ELEVATION_M):
        return None
    default_name = "Col" if col_type == "col" else "Sommet"
    return {
        "osm_id": element["id"],
        "name": (tags.get("name") or f"{default_name} (OSM #{element['id']})")[:_MAX_NAME_LENGTH],
        "latitude": element["lat"],
        "longitude": element["lon"],
        "elevation_m": elevation_m,
        "type": col_type,
        "fetched_at": _now().isoformat(),
    }


def fetch_cols_in_bbox(south: float, west: float, north: float, east: float) -> None:
    """Fetch cols/peaks inside a bbox from Overpass and upsert them into `cols`.

    Stateless one-shot fetch used by the per-activity matching pipeline — no home
    cache involved (that is `refresh_nearby_cols`'s job). Network errors propagate:
    the caller decides how to react (typically: keep the matching cursor behind the
    failed activity so it is retried on the next cron run).
    """
    db = get_admin_client()
    response = _overpass_get(_build_bbox_query(south, west, north, east))
    elements = response.json().get("elements", [])

    rows: list[dict[str, Any]] = []
    for element in elements:
        row = _element_to_row(element)
        if row is not None:
            rows.append(row)
    if rows:
        db.table("cols").upsert(rows, on_conflict="osm_id").execute()


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

    response = _overpass_get(_build_query(home_lat, home_lon))
    elements = response.json().get("elements", [])

    rows: list[dict[str, Any]] = []
    for element in elements:
        row = _element_to_row(element)
        if row is not None:
            rows.append(row)
    if rows:
        db.table("cols").upsert(rows, on_conflict="osm_id").execute()

    db.table("athlete_profiles").update(
        {
            "cols_cache_updated_at": _now().isoformat(),
            "cols_cache_home_lat": home_lat,
            "cols_cache_home_lon": home_lon,
        }
    ).eq("user_id", user_id).execute()
