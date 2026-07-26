"""Compute the user's home location from the median of GPS activity start points."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any, cast

from garmin_sync.supabase_client import get_admin_client

# Médiane sur les N sorties GPS les plus récentes : borne le payload (route_polyline
# est une colonne JSONB relue à chaque sync), reste sous le cap serveur PostgREST
# (~1000 lignes, tronqué silencieusement), et suit le domicile si l'athlète déménage.
_RECENT_GPS_ACTIVITIES_LIMIT = 200


def compute_home_location(user_id: str) -> tuple[float, float] | None:
    """Recompute and persist the user's home (lat, lon) from GPS activity history.

    Uses the first point of each activity's `route_polyline` (already downsampled at
    sync time), bounded to the most recent GPS activities. Writes `lat`, `lon`,
    `home_computed_at` on `athlete_profiles`. Returns the computed `(lat, lon)`, or
    `None` if the user has no GPS activity yet — in that case the profile is left
    untouched.
    """
    db = get_admin_client()
    rows = cast(
        "list[dict[str, Any]]",
        db.table("activities")
        .select("route_polyline")
        .eq("user_id", user_id)
        .not_.is_("route_polyline", "null")
        .order("start_time", desc=True)
        .limit(_RECENT_GPS_ACTIVITIES_LIMIT)
        .execute()
        .data
        or [],
    )

    lats: list[float] = []
    lons: list[float] = []
    for row in rows:
        polyline = row.get("route_polyline")
        if not isinstance(polyline, list) or not polyline:
            continue
        first = polyline[0]
        if not isinstance(first, list) or len(first) < 2:
            continue
        lons.append(float(first[0]))
        lats.append(float(first[1]))

    if not lats:
        return None

    home_lat = statistics.median(lats)
    home_lon = statistics.median(lons)

    db.table("athlete_profiles").update(
        {
            "lat": home_lat,
            "lon": home_lon,
            "home_computed_at": datetime.now(UTC).isoformat(),
        }
    ).eq("user_id", user_id).execute()

    return home_lat, home_lon
