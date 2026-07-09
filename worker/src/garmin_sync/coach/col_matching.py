"""Match GPS activities against nearby cols by proximity to the summit point."""

from __future__ import annotations

from typing import Any, cast

from garmin_sync.coach.geo import haversine_m
from garmin_sync.supabase_client import get_admin_client

DbRows = list[dict[str, Any]]

_NEARBY_RADIUS_M = 50_000
_CROSSING_THRESHOLD_M = 150.0


def recompute_col_crossings(user_id: str, home_lat: float, home_lon: float) -> None:
    """Detect col crossings on GPS activities synced since the last run.

    Processes activities with `start_time` after `col_matching_cursor` (or the full
    history on first run), matches each against cols within 50km of home using
    full-resolution `activity_samples`, and upserts one `col_crossings` row per
    (col, activity) pair within 150m. Advances the cursor to the latest processed
    activity's `start_time`.

    Note: `col_matching_cursor` only guards against re-scanning already-processed
    activities, not against re-matching them when a new col is added to the shared
    `cols` table later (e.g. a periodic Overpass refresh). A col added after an
    activity's cursor has passed is never matched against that activity again, so
    it can show "0 fois" even if the user actually rode past it. Accepted limitation
    for this gadget feature.
    """
    db = get_admin_client()

    nearby_cols = _fetch_nearby_cols(db, home_lat, home_lon)
    if not nearby_cols:
        return

    cursor = _fetch_cursor(db, user_id)
    activities = _fetch_pending_activities(db, user_id, cursor)
    if not activities:
        return

    max_start_time: str | None = cursor
    for activity in activities:
        start_time = activity["start_time"]
        _process_activity(db, user_id=user_id, activity=activity, cols=nearby_cols)
        if max_start_time is None or start_time > max_start_time:
            max_start_time = start_time

    if max_start_time is not None and max_start_time != cursor:
        db.table("athlete_profiles").update({"col_matching_cursor": max_start_time}).eq(
            "user_id", user_id
        ).execute()


def _fetch_nearby_cols(db: Any, home_lat: float, home_lon: float) -> DbRows:
    all_cols = cast(
        DbRows,
        db.table("cols").select("id, latitude, longitude").execute().data or [],
    )
    return [
        col
        for col in all_cols
        if haversine_m(home_lat, home_lon, float(col["latitude"]), float(col["longitude"]))
        <= _NEARBY_RADIUS_M
    ]


def _fetch_cursor(db: Any, user_id: str) -> str | None:
    profile_response = (
        db.table("athlete_profiles")
        .select("col_matching_cursor")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    profile = cast("dict[str, Any] | None", profile_response.data if profile_response else None)
    return profile.get("col_matching_cursor") if profile else None


def _fetch_pending_activities(db: Any, user_id: str, cursor: str | None) -> DbRows:
    query = (
        db.table("activities")
        .select("garmin_activity_id, start_time")
        .eq("user_id", user_id)
        .not_.is_("route_polyline", "null")
    )
    if cursor:
        query = query.gt("start_time", cursor)
    return cast(DbRows, query.order("start_time").execute().data or [])


def _process_activity(db: Any, *, user_id: str, activity: dict[str, Any], cols: DbRows) -> None:
    # One `activity_samples` query per activity (N+1) is deliberate here, not an
    # oversight: batching all activities' samples into a single `.in_(...)` query
    # would multiply the row count returned per request, making it *more* likely to
    # hit PostgREST's server-side row cap and silently truncate — exactly the
    # correctness risk the per-activity `.limit(5000)` below was added to prevent.
    # This runs in the nightly background cron (not a user-facing request path), and
    # the cursor bounds it to a handful of new activities per user per day after the
    # first backfill run, so the extra round-trips are an acceptable trade for
    # guaranteed-bounded, non-truncating reads.
    activity_id = activity["garmin_activity_id"]
    start_time = activity["start_time"]
    samples = cast(
        DbRows,
        db.table("activity_samples")
        .select("latitude, longitude")
        .eq("user_id", user_id)
        .eq("garmin_activity_id", activity_id)
        .not_.is_("latitude", "null")
        .limit(5000)
        .execute()
        .data
        or [],
    )
    crossing_rows = _match_activity(
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        samples=samples,
        cols=cols,
    )
    if crossing_rows:
        db.table("col_crossings").upsert(
            crossing_rows, on_conflict="user_id,col_id,garmin_activity_id"
        ).execute()


def _match_activity(
    *,
    user_id: str,
    activity_id: int,
    start_time: str,
    samples: DbRows,
    cols: DbRows,
) -> DbRows:
    rows: DbRows = []
    for col in cols:
        distances = (
            haversine_m(
                float(sample["latitude"]),
                float(sample["longitude"]),
                float(col["latitude"]),
                float(col["longitude"]),
            )
            for sample in samples
        )
        min_distance = min(distances, default=None)
        if min_distance is not None and min_distance <= _CROSSING_THRESHOLD_M:
            rows.append(
                {
                    "user_id": user_id,
                    "col_id": col["id"],
                    "garmin_activity_id": activity_id,
                    "crossed_at": start_time,
                    "min_distance_m": round(min_distance, 1),
                }
            )
    return rows
